"""
Project 3: Contagion
Name: Amanda Hoelting
Date: 1/30/2023
"""


"""Simple grid model of contagion"""

import mvc  # for Listenable
import enum
import random
import config
from typing import List, Tuple

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)



class Health(enum.Enum):
    """Each individual is one discrete state of health"""
    vulnerable = enum.auto()
    asymptomatic = enum.auto()
    symptomatic = enum.auto()
    recovered = enum.auto()
    dead = enum.auto()

    def __str__(self) -> str:
        return self.name


class Individual(mvc.Listenable):
    """An individual in the population,
    e.g., a person who might get and spread a disease.
    The 'state' instance variable is public read-only, e.g.,
    listeners can check it.
    """

    def __init__(self, kind: str,
                 region: "Population", row: int, col: int):
        # Listener needs its own initialization
        super().__init__()
        self.kind = kind
        self.region = region
        self.row = row
        self.col = col
        # Initially we are 'vulnerable', not yet infected
        self._time_in_state = 0  # How long in this state?
        self.state = Health.vulnerable
        self.next_state = Health.vulnerable
        # Configuration parameters based on kind
        self.T_Incubate = config.get_int(kind, "T_Incubate")
        self.P_Transmit = config.get_float(kind, "P_Transmit")
        self.T_Recover = config.get_int(kind, "T_Recover")
        self.P_Death = config.get_float(kind, "P_Death")
        self.P_Greet = config.get_float(kind, "P_Greet")
        self.N_Neighbors = config.get_int(kind, "N_Neighbors")
        self.P_Visit = config.get_float(kind, "P_Visit")
        self.Visit_Dist = config.get_int(kind, "Visit_Dist")
        self.neighbors = region.neighbors(num=self.N_Neighbors,
                                          row=row, col=col,
                                          dist=self.Visit_Dist)

    def step(self):
        """Next state"""
        # Basic state transitions are in common
        if self.state == Health.asymptomatic:
            if self._time_in_state > self.T_Incubate:
                self.next_state = Health.symptomatic
                log.debug("Becoming symptomatic")
        if self.state == Health.symptomatic:
            # We could die on any time step before we recover
            if self._time_in_state > self.T_Recover:
                log.debug(f"Recovery at {self.row},{self.col}")
                self.next_state = Health.recovered
            elif random.random() < self.P_Death:
                log.debug(f"Death at {self.row},{self.col}")
                self.next_state = Health.dead
        # Social behavior differs among concrete classes
        self.social_behavior()


    def infect(self):
        """Called by another individual spreading germs.
        May also be called on "patient 0" to start simulation.
        """
        if self.state == Health.vulnerable:
            self.next_state = Health.asymptomatic

    def tick(self):
        """Time passes"""
        self._time_in_state += 1
        if self.state != self.next_state:
            self.state = self.next_state
            self.notify_all("newstate")
            # Reset clock
            self._time_in_state = 0

    def meet(self, other: "Individual"):
        """Two individuals meet.  Either may infect
        the other.
        """
        self.maybe_transmit(other)  # I might infect you
        other.maybe_transmit(self)  # You might infect me

    def maybe_transmit(self, other: "Individual"):
        if not self._is_contagious():
            return
        if not other.state == Health.vulnerable:
            return
        # Transmission is possible.  Roll the dice
        if random.random() < self.P_Transmit:
            other.infect()

    def _is_contagious(self) -> bool:
        """SARS COVID 19 apparently spreads before
        the individual is symptomatic.
        """
        return (self.state == Health.symptomatic
                or self.state == Health.asymptomatic)

    def hello(self, visitor: "Individual") -> bool:
        """True means 'welcome' and False means 'go away'"""
        raise NotImplementedError("Each class must implement 'hello'")

    def social_behavior(self):
        raise NotImplementedError("Social behavior should be implemented in subclasses")

class Typical(Individual):
    """Typical individual. May visit different neighbors
    each day.
    """
    def __init__(self, region: "Population", row: int, col: int):
        # Much of the constructor has been "factored out" into
        # the abstract base class
        super().__init__("Typical", region, row, col)

    def social_behavior(self):
        """A typical individual visits neighbors at random"""
        if random.random() < self.P_Visit:
            addr = random.choice(self.neighbors)
            neighbor = self.region.visit(addr)
            if neighbor.hello(self):
                neighbor.meet(self)

    def hello(self, visitor: "Individual") -> bool:
        """True means 'welcome' and False means 'go away'"""
        return True
class Wanderer(Individual):
    """Wandering individual. May visit different "neighbors"
    each day that are far away.
    """
    def __init__(self, region: "Population", row: int, col: int):
        # Much of the constructor has been "factored out" into
        # the abstract base class
        super().__init__("Wanderer", region, row, col)

    def social_behavior(self):
        """A wandering individual visits neighbors at random at
        farther distances away."""
        if random.random() < self.P_Visit:
            addr = random.choice(self.neighbors)
            neighbor = self.region.visit(addr)
            if neighbor.hello(self):
                neighbor.meet(self)

    def hello(self, visitor: "Individual") -> bool:
        """True means 'welcome' and False means 'go away'"""
        return True


class AtRisk(Individual):
    """Immunocompromised or elderly.
    Vulnerable and cautious.
    """
    def __init__(self, region: "Population", row: int, col: int):
        # Much of the constructor has been "factored out" into
        # the abstract base class
        super().__init__("AtRisk", region, row, col)
        self.prior_visit = None

    def social_behavior(self):
        """The way an AtRisk individual interacts with neighbors"""
        if random.random() >= self.P_Visit:
            # No visits today!
            return
        if self.prior_visit is None:
            # Time for someone new
            addr = random.choice(self.neighbors)
            neighbor = self.region.visit(addr)
            self.prior_visit = neighbor
        else:
            # Second visit to the same person
            neighbor = self.prior_visit
            self.prior_visit = None
        if neighbor.hello(self):
            neighbor.meet(self)

    def hello(self, visitor: "Individual") -> bool:
        """True means 'welcome' and False means 'go away'"""
        if (visitor.row, visitor.col) in self.neighbors:
            return True
        else:
            return False


class Population(mvc.Listenable):
    def __init__(self, rows: int, cols: int):
        super().__init__()
        self.cells = []
        self.nrows = rows
        self.ncols = cols
        # Populate according to configuration
        for row_i in range(config.get_int("Grid", "Rows")):
            row = []
            for col_i in range(config.get_int("Grid", "Cols")):
                row.append(self._random_individual(row_i, col_i))
            self.cells.append(row)
        return


    def step(self):
        """Determine next states"""
        log.debug("Population: Step")
        # Time passes
        for row in self.cells:
            for cell in row:
                cell.step()
        for row in self.cells:
            for cell in row:
                cell.tick()
        self.notify_all("timestep")


    def seed(self):
        """Patient zero"""
        row = random.randint(0, self.nrows - 1)
        col = random.randint(0, self.ncols - 1)
        self.cells[row][col].infect()
        self.cells[row][col].tick()

    def count_in_state(self, state: Health) -> int:
        """How many individuals are currently in state?"""
        state_count = 0
        for row in self.cells:
            for cell in row:
                if cell.state == state:
                    state_count += 1
        return state_count

    def _random_individual(self, row: int, col: int) -> "Individual":
        """Generates random individual"""
        classes = [(AtRisk, config.get_float("Grid", "Proportion_AtRisk")),
                   (Typical, config.get_float("Grid", "Proportion_Typical")),
                   (Wanderer, config.get_float("Grid", "Proportion_Wanderer"))]
        while True:
            for the_class, proportion in classes:
                dice = random.random()
                if dice < proportion:
                    return the_class(self, row, col)

    def neighbors(self, num: int, row: int, col: int, dist: int) -> List[Tuple[int, int]]:
        """Give me addresses of up to num neighbors
        up to dist away from here(Manhattan distance)
        """
        result = []
        count = 0
        #log.debug(f"Cell {row},{col} finding {num} neighbors at distance {dist} " +
                  #f"in {self.nrows},{self.ncols}")
        attempts = 0
        while count < num:
            attempts += 1
            assert attempts < 1000, (
                f"Can't find {num} neighbors at distance {dist}")
            row_step = random.randint(0 - dist, dist)
            col_step = random.randint(0 - dist, dist)
            row_addr = row + row_step
            col_addr = col + col_step
            # log.debug(f"Trying neighbor at position {row_addr},{col_addr}")
            if row_addr < 0 or row_addr >= self.nrows:
                # log.debug("Bad row")
                continue
            if col_addr < 0 or col_addr >= self.ncols:
                # log.debug("Bad column")
                continue
            if row_addr == row and col_addr == 0:
                # log.debug("Can't visit self")
                continue
            neighbor_addr = (row_addr, col_addr)
            if neighbor_addr in result:
                continue
            #log.debug(f"{row},{col} adding neighbor at {row_addr},{col_addr}")
            result.append(neighbor_addr)
            count += 1
        return result

    def visit(self, address: Tuple[int, int]):
        """Who lives there?"""
        row_num, col_num = address
        return self.cells[row_num][col_num]




