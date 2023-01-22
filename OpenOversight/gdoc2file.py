#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Import script - pulls from google sheet, parses, and writes to a csv."""

from dotenv import load_dotenv, find_dotenv
import uuid

import os.path
import sys

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, exc
from sqlalchemy.sql import text

load_dotenv(find_dotenv())
# The ID and range of the spreadsheet to sample.
SAMPLE_SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
SAMPLE_RANGE = '!A2:M'

API_KEY = os.environ.get('API_KEY')

# build a table mapping all non-printable characters to None
NOPRINT_TRANS_TABLE = {
    i: None for i in range(0, sys.maxunicode + 1) if not chr(i).isprintable()
}

all_rows = []
try:
    service = build('sheets', 'v4', developerKey=API_KEY)

    # get sheet names
    sheet_metadata = service.spreadsheets()\
        .get(spreadsheetId=SAMPLE_SPREADSHEET_ID).execute()
    sheets = sheet_metadata.get('sheets', '')
    sheet_names = [s['properties']['title'] for s in sheets]
    try:     # ignore these sheets
        sheet_names.remove('Updates')
        sheet_names.remove('Dashboard')
    except ValueError:
        print("Error: Updates or Dashboard sheets are missing, ignoring")

    sheet = service.spreadsheets()
    for sn in sheet_names:
        result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                                    range=sn + SAMPLE_RANGE,
                                    ).execute()
        values = result.get('values', [])
        # print(f"{len(values)} rows in sheet {sn}")
        all_rows.extend(values)

except HttpError as err:
    print(err)
    exit(2)

print("%s records total", len(all_rows))

# strip non-printable chars from all input data
all_rows = [[y.translate(NOPRINT_TRANS_TABLE) for y in x] for x in all_rows]

df = pd.DataFrame(all_rows)

df.columns = ['last', 'first', 'mi', 'photo', 'badge', 'job_title',
              'unit', 'gender', 'race', 'hired', 'salary',
              'department', 'uuid']
# remove header rows
df = df.loc[df['photo'] != 'Photo']
# also drop any rows with a null department
# (usually just the department name rows)
df = df.dropna(subset=['department'])

# clean Badge field
df.badge = df.badge.fillna('').str.strip()
# set blank first names to "n/a"
df.loc[df['first'].isna(), 'first'] = 'n/a'

engine = create_engine(os.environ.get('SQLALCHEMY_DATABASE_URI'))

# insert any missing reference data first
# dept
df = df.set_index('department')
df.index.name = 'department'
with engine.connect() as connection:
    ddf = pd.read_sql('select * from departments', connection)\
        .set_index('name')
    # first, insert any departments that aren't in the master dept list
    for d in list(df.loc[~df.index.isin(ddf.index)].index.unique()):
        s = text("""insert into departments (name, short_name)
         values (:department, :department)""")
        result = connection.execute(s, department=d)
    ddf = pd.read_sql('select * from departments', connection)\
        .set_index('name')
# then add all dept ids to the main df
df['dept_id'] = df.apply(lambda x: ddf.loc[x.name].id, 1)
df.reset_index(inplace=True)

# same with units, for the department
with engine.connect() as connection:
    udf = pd.read_sql('select * from unit_types', connection)
# can't have a blank unit, so fill in Unknown
df['unit'] = df['unit'].fillna('Unknown')
# merged units
mudf = pd.merge(df, udf, left_on=['dept_id', 'unit'],
                right_on=['department_id', 'descrip'], how='left')
# find units which aren't in the database list yet (no unit_id)
idf = mudf.loc[mudf['id'].isna(), ['unit', 'dept_id']].drop_duplicates()
# and insert them
with engine.connect() as connection:
    for index, unit in idf.iterrows():
        s = text("""insert into unit_types (descrip, department_id)
                values (:descrip, :department_id)""")
        result = connection.execute(s, descrip=unit['unit'],
                                    department_id=unit['dept_id'])
    udf = pd.read_sql('select * from unit_types', connection)
# ok, now they're all in the db. remake merged df
mudf = pd.merge(df, udf, left_on=['dept_id', 'unit'],
                right_on=['department_id', 'descrip'], how='left')
# and neatly add those ids back into parent df
mudf = mudf.set_index(['dept_id', 'unit'])\
    .rename(columns={'id': 'unit_id'})['unit_id']\
    .drop_duplicates().astype('Int64')
df = df.set_index(['dept_id', 'unit'])
df = df.join(mudf, how='left').reset_index()


# once more with job_title
with engine.connect() as connection:
    jdf = pd.read_sql('select * from jobs', connection)
# also can't have a blank job title
df['job_title'] = df['job_title'].fillna('Not Sure')
mjdf = pd.merge(df, jdf, left_on=['dept_id', 'job_title'],
                right_on=['department_id', 'job_title'], how='left')
mjdf = mjdf.loc[~mjdf['job_title'].isna(), :]
# jobs (for dept) not in db
idf = mjdf.loc[mjdf['id'].isna(), ['dept_id', 'department_id', 'job_title']]\
    .drop_duplicates()
with engine.connect() as connection:  # insert them
    for index, job in idf.iterrows():
        s = text("""insert into jobs (job_title, \"order\", department_id)
                values (:job_title, (select coalesce(max(j.\"order\")+1,0)
                from jobs j
                where j.department_id = :department_id),
                :department_id)""")
        result = connection.execute(s, job_title=job['job_title'],
                                    department_id=job['dept_id'])
# also create a "Not Sure" job as a default for each dept
with engine.connect() as connection:
    nsi = idf.loc[idf['department_id'].isna(), 'dept_id'].drop_duplicates()
    for d in list(nsi):
        try:
            s = text("""insert into jobs (job_title, \"order\", department_id)
                    values (:job_title, (select coalesce(max(j.\"order\")+1,0)
                    from jobs j
                    where j.department_id = :department_id),
                    :department_id)""")
            result = connection.execute(s, job_title='Not Sure',
                                        department_id=d)
        except exc.SQLAlchemyError:
            pass  # failures are fine
    # reload after inserts
    jdf = pd.read_sql('select * from jobs', connection)
# ok, now they're all in the db

# get unique id from db officers list
with engine.connect() as connection:
    odf = pd.read_sql('''select o.*, a.star_no,
        j.job_title,
        a.unit_id
        from officers o
        left join (select a2.*,
                    min(a2.id) over (partition by a2.officer_id) as minaid
                    from assignments a2) a
            on a.officer_id = o.id and a.id = minaid
        left join jobs j
        on j.id = a.job_id
        and j.department_id = o.department_id
    ''', connection)
odf.replace([None], np.nan, inplace=True)

modf = odf.loc[:, ['department_id', 'last_name', 'first_name',
                   'middle_initial', 'suffix', 'star_no',
                   'unique_internal_identifier']]
modf.columns = ['dept_id', 'last', 'first', 'mi', 'suffix',
                'badge', 'unique_internal_identifier']

# try exact match first
df['uuid'] = df['uuid'].fillna('')
df['unique_internal_identifier'] = \
    pd.merge(df, modf,
             left_on='uuid',
             right_on='unique_internal_identifier',
             how='left')['unique_internal_identifier']

# create lowercase name fields for both (with no special characters) 
# to match on - l f m s
df = pd.concat([df, df[['last','first','mi','suffix']]\
    .apply(lambda x: x.fillna('').str.lower().str.replace('[^a-z]', '', regex=True))\
    .rename(columns=lambda x: x[0])], axis=1)
modf = pd.concat([modf, modf[['last','first','mi','suffix']]\
    .apply(lambda x: x.fillna('').str.lower().str.replace('[^a-z]', '', regex=True))\
    .rename(columns=lambda x: x[0])], axis=1)
df.loc[:,['l', 'f', 'm', 's']].fillna('', inplace=True)
modf.loc[:,['l', 'f', 'm', 's']].fillna('', inplace=True)


modf = modf.set_index(['dept_id', 'l', 'f', 'm', 's', 'badge'])
df = df.set_index(['dept_id', 'l', 'f', 'm', 's', 'badge'])
df['uuid1'] = df.join(modf['unique_internal_identifier'], how='left', lsuffix='1')['unique_internal_identifier']
df['unique_internal_identifier'].fillna(df['uuid1'], inplace=True)
# it would be nice if we could update the sheet with this
modf.reset_index(inplace=True)
df.reset_index(inplace=True)

# second try - match without badge
modf = modf.set_index(['dept_id', 'l', 'f', 'm', 's'])
df = df.set_index(['dept_id', 'l', 'f', 'm', 's'])
#df.loc[:,['unique_internal_identifier']].fillna(modf['unique_internal_identifier'], inplace=True)
df['uuid2'] = df.join(modf['unique_internal_identifier'], how='left', lsuffix='1')['unique_internal_identifier']
df['unique_internal_identifier'].fillna(df['uuid2'], inplace=True)
modf.reset_index(inplace=True)
df.reset_index(inplace=True)

# third try - match first letter of middle name/initial
modf['mi_true'] = modf['m'].str[0].fillna('')
df['mi_true'] = df['m'].str[0].fillna('')
modf = modf.set_index(['dept_id', 'l', 'f', 'mi_true', 's'])
df = df.set_index(['dept_id', 'l', 'f', 'mi_true', 's'])
#df.loc[:,['unique_internal_identifier']].fillna(modf['unique_internal_identifier'], inplace=True)
df['uuid3'] = df.join(modf['unique_internal_identifier'], how='left', lsuffix='1')['unique_internal_identifier']
df['unique_internal_identifier'].fillna(df['uuid3'], inplace=True)
modf.reset_index(inplace=True)
df.reset_index(inplace=True)

# if there's duplicate uuids, drop all but the first one
df.loc[df.duplicated(['unique_internal_identifier']),
       'unique_internal_identifier'] = np.nan
# fill in a unique id for officers missing a badge# and uuid
df.loc[((df['badge'] == '') & (df['unique_internal_identifier'].isna())),
       'unique_internal_identifier'] = \
    df.loc[((df['badge'] == '') &
           (df['unique_internal_identifier'].isna())),
           'unique_internal_identifier']\
    .apply(lambda z: str(uuid.uuid4()))

# required fields for salary to work
df['salary_year'] = 2022    # datetime.now().year
df['salary_is_fiscal_year'] = 'true'
df['salary'] = df['salary'].str.replace('$', '', regex=False)\
    .str.replace(',', '', regex=False)\
    .str.replace(' ', '', regex=False)\
    .str.replace('/', '', regex=False)\
    .str.lower().replace('[A-Za-z]', '', regex=True)

# fix hire dates, throwing out incomprehensible ones
df['hired'] = pd.to_datetime(df['hired'], errors='coerce')\
    .dt.strftime('%m/%d/%Y')

df_export = df.loc[:, ['last',
                       'first',
                       'mi',
                       'gender',
                       'race',
                       'hired',
                       'job_title',
                       'badge',
                       'salary',
                       'dept_id',
                       'unit_id',
                       'unique_internal_identifier',
                       'salary_year',
                       'salary_is_fiscal_year']]
# these names need to match the field names in
# commands.py/bulk_add_officers etc
df_export.columns = ['last_name',
                     'first_name',
                     'middle_initial',
                     'gender',
                     'race',
                     'employment_date',  # hired
                     'job_title',
                     'star_no',  # badge
                     'salary',
                     'department_id',
                     'unit_id',
                     'unique_internal_identifier',
                     'salary_year',
                     'salary_is_fiscal_year']

df_export.to_csv('gsheets_export.csv', index=False)


