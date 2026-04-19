from enum import Enum


class Intent(Enum):
    ADD          = 'add'
    QUERY_TODAY  = 'query_today'
    QUERY_DATE   = 'query_date'
    QUERY_WEEK   = 'query_week'
    QUERY_DETAIL = 'query_detail'
    QUERY_SEARCH = 'query_search'
    CONFIRM_YES  = 'confirm_yes'
    CONFIRM_NO   = 'confirm_no'
    HELP         = 'help'
    UNKNOWN      = 'unknown'
