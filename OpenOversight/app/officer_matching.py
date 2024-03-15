from flask import current_app
from OpenOversight.app.models.database import (db, DupOfficerMatches, Officer, Department)

import recordlinkage
from recordlinkage.preprocessing import clean
import pandas as pd

def duplicate_officer_bulk_search():
    engine = db.engine
    with engine.connect() as conn:
        df = pd.read_sql("""
select o.id, o.last_name, o.first_name, o.middle_initial, o.suffix, o.race, o.gender,
    o.department_id, d.locality_fips as fips
from officers o
join departments d on d.id = o.department_id""", conn)
        df.set_index('id', inplace=True)
        # this one is to retain the exclusions between refreshes
        ex_df = pd.read_sql("""select id_1, id_2, excluded from dup_officer_matches where excluded is not null""", conn)
        ex_df.set_index(['id_1', 'id_2'], inplace=True)
    # 
    # step 1 - clean
    df['last_name'] = clean(df['last_name'])
    df['first_name'] = clean(df['first_name'])
    df['middle_initial'] = clean(df['middle_initial'])
    df['suffix'] = clean(df['suffix'])
    # feature gen
    df['first_initial'] = df['first_name'].str[:1]
    #
    # 2 - block by last name to reduce cartesian product size
    indexer = recordlinkage.Index()
    indexer.block("last_name")
    candidate_links = indexer.index(df)
    current_app.logger.info(f"officer_matching - candidate_links size: {candidate_links.shape}")
    #
    # 3 - set up comparison rules
    compare_cl = recordlinkage.Compare()
    compare_cl.exact("first_name", "first_name", label="first_name")
    compare_cl.string(
        "first_name", "first_name", method="jarowinkler", threshold=0.85, label="fuzzy_first"
    )
    compare_cl.exact("first_initial","first_initial",label="first_initial")
    compare_cl.string(
        "middle_initial", "middle_initial", method="jarowinkler", threshold=0.85, label="fuzzy_mi"
    )
    f = "suffix"
    compare_cl.exact(f, f, label=f)
    f = "gender"
    compare_cl.exact(f, f, label=f)
    f = "race"
    compare_cl.exact(f, f, label=f)
    f = "fips"
    compare_cl.exact(f, f, label=f)
    f = "department_id"
    compare_cl.exact(f, f, label=f)
    # do the comparison - this takes a minute
    features = compare_cl.compute(candidate_links, df) 
    #
    # 
    dist = features.sum(axis=1).value_counts().sort_index(ascending=False)
    current_app.logger.info(f"officer_matching - match distribution: {dist}")
    matches = features[features.sum(axis=1) > 5]
    out_df = pd.DataFrame(matches.sum(axis=1), columns=['match_score'])
    out_df = out_df.join(ex_df, how='left').fillna(False)
    # only keep top 100 matches for performance reasons
    out_df = out_df.sort_values(['excluded','match_score'], ascending=[False,False]).head(100) 
    with engine.connect() as conn:
        out_df.to_sql('dup_officer_matches', if_exists='replace', con=conn)


def merge_officers(keep_me, delete_me):
    current_app.logger.info(f"Merging officer: {delete_me} into {keep_me}")
    strfields = ['last_name','first_name','middle_initial','suffix']
    ofields = ['race','gender','employment_date','birth_year','face']
    rels = ['assignments','salaries','links','incidents','lawsuits','tags','notes','descriptions']
    # merge string fields where we want to keep the longest one
    for sf in strfields:
        keep_sf = getattr(keep_me,sf)
        keep_sf = keep_sf if keep_sf is not None else ""
        del_sf = getattr(delete_me,sf)
        del_sf = del_sf if del_sf is not None else ""
        if len(keep_sf) < len(del_sf): # if delete_me has a longer string,
            setattr(keep_me,sf, del_sf) # use that
    # merge other fields - replace when null
    for o in ofields:
        if getattr(keep_me,o) is None and getattr(delete_me,o) is not None:
            setattr(keep_me, o, getattr(delete_me,o))
    # merge relationships - combine lists
    for r in rels:
        setattr(keep_me, r, (getattr(keep_me,r)+getattr(delete_me,r)))
    db.session.add(keep_me)
    db.session.delete(delete_me)
    db.session.commit()