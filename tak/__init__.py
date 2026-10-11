from decimal import DefaultContext, ROUND_HALF_UP

# Commercial rounding for every money calculation in this project.
# Thread-local contexts copy DefaultContext when they are first used.
DefaultContext.rounding = ROUND_HALF_UP
