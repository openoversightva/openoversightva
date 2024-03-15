"""Contains choice lists of (value, label) tuples for form Select fields."""

AGE_CHOICES = [(str(age), str(age)) for age in range(16, 101)]

GENDER_CHOICES = [
    ("Not Sure", "Not Sure"),
    ("M", "Male"),
    ("F", "Female"),
    ("Other", "Other"),
]

LINK_CHOICES = [
    ("", ""),
    ("link", "Link"),
    ("video", "YouTube Video"),
    ("other_video", "Other Video"),
]

RACE_CHOICES = [
    ("BLACK", "Black"),
    ("WHITE", "White"),
    ("ASIAN", "Asian"),
    ("HISPANIC", "Hispanic"),
    ("NATIVE AMERICAN", "Native American"),
    ("PACIFIC ISLANDER", "Pacific Islander"),
    ("Other", "Other"),
    ("Not Sure", "Not Sure"),
]

# converted from us.states.STATES to avoid problematic us dependency
STATE_CHOICES = [('AL', 'Alabama'),
 ('AK', 'Alaska'),
 ('AZ', 'Arizona'),
 ('AR', 'Arkansas'),
 ('CA', 'California'),
 ('CO', 'Colorado'),
 ('CT', 'Connecticut'),
 ('DE', 'Delaware'),
 ('FL', 'Florida'),
 ('GA', 'Georgia'),
 ('HI', 'Hawaii'),
 ('ID', 'Idaho'),
 ('IL', 'Illinois'),
 ('IN', 'Indiana'),
 ('IA', 'Iowa'),
 ('KS', 'Kansas'),
 ('KY', 'Kentucky'),
 ('LA', 'Louisiana'),
 ('ME', 'Maine'),
 ('MD', 'Maryland'),
 ('MA', 'Massachusetts'),
 ('MI', 'Michigan'),
 ('MN', 'Minnesota'),
 ('MS', 'Mississippi'),
 ('MO', 'Missouri'),
 ('MT', 'Montana'),
 ('NE', 'Nebraska'),
 ('NV', 'Nevada'),
 ('NH', 'New Hampshire'),
 ('NJ', 'New Jersey'),
 ('NM', 'New Mexico'),
 ('NY', 'New York'),
 ('NC', 'North Carolina'),
 ('ND', 'North Dakota'),
 ('OH', 'Ohio'),
 ('OK', 'Oklahoma'),
 ('OR', 'Oregon'),
 ('PA', 'Pennsylvania'),
 ('RI', 'Rhode Island'),
 ('SC', 'South Carolina'),
 ('SD', 'South Dakota'),
 ('TN', 'Tennessee'),
 ('TX', 'Texas'),
 ('UT', 'Utah'),
 ('VT', 'Vermont'),
 ('VA', 'Virginia'),
 ('WA', 'Washington'),
 ('WV', 'West Virginia'),
 ('WI', 'Wisconsin'),
 ('WY', 'Wyoming')]
DEPARTMENT_STATE_CHOICES = [("FA", "Federal Agency")] + STATE_CHOICES

SUFFIX_CHOICES = [
    ("", "-"),
    ("Jr", "Jr"),
    ("Sr", "Sr"),
    ("II", "II"),
    ("III", "III"),
    ("IV", "IV"),
    ("V", "V"),
]
