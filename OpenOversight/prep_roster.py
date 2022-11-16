#!/usr/bin/python

# the "flask bulk-add-officers <file>" command expects the department, and unit fields to already exist in the db.

# input expects: csv with columns (in any order):
# last_name,first_name,middle_initial,star_no,job_title,unit,gender,race,employment_date,salary,department

# outputs file: ready.csv in current directory, with columns:
# last_name,first_name,middle_initial,star_no,job_title,gender,race,employment_date,salary,department_id,unit_id

# afterwards, run: flask bulk-add-officers ready.csv


import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.sql import text
from dotenv import load_dotenv, find_dotenv
import random
from string import digits


load_dotenv(find_dotenv())

filename = sys.argv[1]
df = pd.read_csv(filename)
df.set_index('department', inplace=True)
df.index.name = 'department'

engine = create_engine(os.environ.get('SQLALCHEMY_DATABASE_URI'))

# departments
with engine.connect() as connection:
    ddf = pd.read_sql('select * from departments', connection).set_index('name')
with engine.connect() as connection:
    # first, insert any departments that aren't in the master dept list
    for d in list(df.loc[~df.index.isin(ddf.index)].index.unique()):
        s = text("insert into departments (name, short_name) values (:department, :department)")
        result = connection.execute(s, department=d)
    ddf = pd.read_sql('select * from departments', connection).set_index('name')
# then apply their ids to the csv
df['dept_id'] = df.apply(lambda x: ddf.loc[x.name].id, 1)
df.reset_index(inplace=True)

# same with units, for the department
with engine.connect() as connection:
    udf = pd.read_sql('select * from unit_types', connection)
# can't have a blank unit, so fill in Unknown
df['unit'] = df['unit'].fillna('Unknown')
# merged units
mudf = pd.merge(df, udf, left_on=['dept_id','unit'], right_on=['department_id','descrip'], how='left')
# find units which aren't in the master list
idf = mudf.loc[mudf['id'].isna(),['unit','dept_id']].drop_duplicates()
with engine.connect() as connection:
    for index, unit in idf.iterrows():
        s = text("insert into unit_types (descrip, department_id) values (:descrip, :department_id)")
        result = connection.execute(s, descrip=unit['unit'], department_id=unit['dept_id'])
    udf = pd.read_sql('select * from unit_types', connection)
# ok, now they're all in the master list. remake merged df
mudf = pd.merge(df, udf, left_on=['dept_id','unit'], right_on=['department_id','descrip'], how='left')
# smush those back into parent df
df['unit_id'] = mudf['id'].astype('Int64')

# once more with job_title
with engine.connect() as connection:
    jdf = pd.read_sql('select * from jobs', connection)
# also can't have a blank job title
df['job_title'] = df['job_title'].fillna('Not Sure')
mjdf = pd.merge(df, jdf, left_on=['dept_id','job_title'], right_on=['department_id','job_title'], how='left')
mjdf = mjdf.loc[~mjdf['job_title'].isna(),:]
# jobs (and dept) not in master list
idf = mjdf.loc[mjdf['id'].isna(),['dept_id','department_id','job_title']].drop_duplicates()
with engine.connect() as connection:
    for index, job in idf.iterrows():
        #print(f"{job}")
        s = text("insert into jobs (job_title, \"order\", department_id) values (:job_title, (select coalesce(max(j.\"order\")+1,0) from jobs j where j.department_id = :department_id), :department_id)")
        result = connection.execute(s, job_title=job['job_title'], department_id=job['dept_id'])
    # also create a "Not Sure" job as a default for each dept
    nsi = idf.loc[idf['department_id'].isna(),'dept_id'].drop_duplicates()
    for d in list(nsi):
        try:
            s = text("insert into jobs (job_title, \"order\", department_id) values (:job_title, (select coalesce(max(j.\"order\")+1,0) from jobs j where j.department_id = :department_id), :department_id)")
            result = connection.execute(s, job_title='Not Sure', department_id=d)
        except:
            pass # failures are fine
    # reload after inserts
    jdf = pd.read_sql('select * from jobs', connection)
# ok, now they're all in the master list. 

# fill in a unique id for officers missing a badge #
#df['unique_internal_identifier'] = ''
#df.loc[df['star_no'].isna(),'unique_internal_identifier'] = df.loc[df['star_no'].isna(),'unique_internal_identifier']\
#    .apply(lambda z: ''.join(random.choice(digits) for x in range(15)))


# the df is ready for the bulk import
df.rename(columns={'dept_id': 'department_id'}, inplace=True)
df.loc[:,['last_name', 'first_name', 'middle_initial', 'star_no',
       'job_title', 'gender', 'race', 'employment_date', 'salary',
       'department_id', 'unit_id']].to_csv('ready.csv',index=False)
