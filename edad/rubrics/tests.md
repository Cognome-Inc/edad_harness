T1 TRACE     every acceptance criterion has >=1 test, and every test
             names the criterion/decision it proves      (gap = MAJOR)
T2 COVERAGE  happy path, error path, and boundaries (empty, max,
             invalid, duplicate, None) for each criterion (gap = MAJOR)
T3 ONE THING one behavior per test                       (MAJOR)
T4 ASSERTS   precise expected values; no bare 'no exception' /
             truthy checks                               (MAJOR)
T5 RED FIRST would fail against the base for the right reason,
             not an import error                         (BLOCKER)
T6 ISOLATED  no order dependence, shared state, network, clock,
             or real home dir                            (MAJOR)
T7 SETUP     preconditions explicit in the test or a named fixture (NIT)
T8 NAMES     name reads as the expected behavior
             (test_<does>_when_<condition>)              (NIT)
