from urllib.parse import urlparse

#from us import states


def state_validator(state):
    # switch to static list to avoid problematic us dependencies
    list_of_states = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']

    if state not in list_of_states and state != "DC" and state is not None:
        raise ValueError("Not a valid US state")

    return state


def url_validator(url):
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        raise ValueError("Not a valid URL")

    return url
