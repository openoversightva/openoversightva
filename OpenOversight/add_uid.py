#!/usr/bin/python

# sometimes the badge number / star_no is blank, and then apparently you need a unique_internal_identifier
# this will add that column and fill it in for all officers

import pandas as pd
import random
from string import digits 

df = pd.read_csv('ready.csv')

# fill in a unique id for officers missing a badge#
df['unique_internal_identifier'] = None
df['unique_internal_identifier'] = df.loc[:,'unique_internal_identifier']\
    .apply(lambda z: ''.join(random.choice(digits) for x in range(15)))

# the df is ready again
df.loc[:,['last_name', 'first_name', 'middle_initial', 'star_no',
       'job_title', 'gender', 'race', 'employment_date', 'salary',
       'department_id', 'unit_id','unique_internal_identifier']].to_csv('ready.csv',index=False)
