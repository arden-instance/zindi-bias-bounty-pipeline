import duckdb, time, pandas as pd, sys

REG = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.sql("SET s3_region='us-west-2'; SET s3_url_style='path';")
BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

SCHOOL_CATS = ['elementary_school', 'middle_school', 'high_school', 'school',
               'private_school', 'public_school']

t0 = time.time()
con.sql(f"CREATE TEMP TABLE tracts AS SELECT GEOID, geometry, bbox FROM '{BASE}/strata/{REG}/{REG}-census-tracts.parquet'")

# Overture POI centroids, pre-split by HIFLD-comparable type. Points, so centroid-in-tract
# (same convention as building_gap.py) rather than road_gap.py's length-clipped intersection.
con.sql(f"""
CREATE TEMP TABLE ov_fire AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-overture-pois.parquet'
WHERE categories.primary = 'fire_department'
""")
con.sql(f"""
CREATE TEMP TABLE ov_ems AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-overture-pois.parquet'
WHERE categories.primary = 'ambulance_and_ems_services'
""")
con.sql(f"""
CREATE TEMP TABLE ov_school AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-overture-pois.parquet'
WHERE categories.primary IN ({",".join("'" + c + "'" for c in SCHOOL_CATS)})
""")
con.sql(f"""
CREATE TEMP TABLE ov_all_poi AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-overture-pois.parquet'
""")
# hospitals deliberately excluded (Overture over-counts ~12x vs HIFLD everywhere, per README)
con.sql(f"""
CREATE TEMP TABLE hifld_fire AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-hifld-fire-stations.parquet'
""")
con.sql(f"""
CREATE TEMP TABLE hifld_ems AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-hifld-ems-stations.parquet'
""")
con.sql(f"""
CREATE TEMP TABLE hifld_school AS
SELECT ST_Centroid(geometry) AS pt FROM '{BASE}/reference/{REG}/{REG}-hifld-schools.parquet'
""")
# CBP is already tract-keyed in the bucket -- no point layer / spatial join needed for this half.
cbp = con.sql(f"""
SELECT GEOID, cbp_estab FROM '{BASE}/reference/{REG}/{REG}-census-cbp.parquet'
""").df()
print("load", time.time() - t0)


def tract_count(table):
    return con.sql(f"""
        SELECT t.GEOID, count(*) AS n
        FROM tracts t JOIN {table} b
        ON t.bbox.xmin <= ST_X(b.pt) AND t.bbox.xmax >= ST_X(b.pt)
        AND t.bbox.ymin <= ST_Y(b.pt) AND t.bbox.ymax >= ST_Y(b.pt)
        AND ST_Contains(t.geometry, b.pt)
        GROUP BY t.GEOID
    """).df()


t0 = time.time()
counts = {
    "ov_fire_n": tract_count("ov_fire"),
    "hifld_fire_n": tract_count("hifld_fire"),
    "ov_ems_n": tract_count("ov_ems"),
    "hifld_ems_n": tract_count("hifld_ems"),
    "ov_school_n": tract_count("ov_school"),
    "hifld_school_n": tract_count("hifld_school"),
    "ov_all_poi_n": tract_count("ov_all_poi"),
}
print("joins", time.time() - t0)

geoids = con.sql("SELECT GEOID FROM tracts").df()
df = geoids.copy()
for col, cdf in counts.items():
    df = df.merge(cdf.rename(columns={"n": col}), on="GEOID", how="left")
    df[col] = df[col].fillna(0).astype(int)
df = df.merge(cbp, on="GEOID", how="left")
df["cbp_estab"] = df["cbp_estab"].fillna(0)


def gap(overture_col, reference_col):
    defined = df[reference_col] > 0
    g = pd.Series(0.0, index=df.index)
    g.loc[defined] = 1 - (df.loc[defined, overture_col] / df.loc[defined, reference_col]).clip(upper=1.0)
    return g, defined


df["poi_gap_fire"], df["poi_gap_fire_defined"] = gap("ov_fire_n", "hifld_fire_n")
df["poi_gap_ems"], df["poi_gap_ems_defined"] = gap("ov_ems_n", "hifld_ems_n")
df["poi_gap_schools"], df["poi_gap_schools_defined"] = gap("ov_school_n", "hifld_school_n")
df["poi_gap_cbp"], df["poi_gap_cbp_defined"] = gap("ov_all_poi_n", "cbp_estab")

hifld_cols = ["poi_gap_fire", "poi_gap_ems", "poi_gap_schools"]
hifld_def = df[["poi_gap_fire_defined", "poi_gap_ems_defined", "poi_gap_schools_defined"]].values
df["poi_gap_hifld"] = (df[hifld_cols].values * hifld_def).sum(axis=1) / hifld_def.sum(axis=1).clip(min=1)
df["poi_gap_hifld"] = df["poi_gap_hifld"].where(hifld_def.sum(axis=1) > 0)

halves = pd.DataFrame({"hifld": df["poi_gap_hifld"], "cbp": df["poi_gap_cbp"].where(df["poi_gap_cbp_defined"])})
df["poi_gap"] = halves.mean(axis=1, skipna=True)
df["poi_defined"] = halves.notna().any(axis=1)

for name, col in [("fire", "poi_gap_fire_defined"), ("ems", "poi_gap_ems_defined"),
                   ("schools", "poi_gap_schools_defined"), ("cbp", "poi_gap_cbp_defined")]:
    n_undef = (~df[col]).sum()
    print(f"{name} undefined: {n_undef}/{len(df)}")
print(f"poi (overall) undefined: {(~df['poi_defined']).sum()}/{len(df)}")
print(df["poi_gap"].describe())
print(f"totals: ov_fire={df.ov_fire_n.sum()} hifld_fire={df.hifld_fire_n.sum()} "
      f"ov_ems={df.ov_ems_n.sum()} hifld_ems={df.hifld_ems_n.sum()} "
      f"ov_school={df.ov_school_n.sum()} hifld_school={df.hifld_school_n.sum()} "
      f"ov_all_poi={df.ov_all_poi_n.sum()} cbp_estab={df.cbp_estab.sum()}")

df.to_csv(f"{REG}_poi_gap.csv", index=False)
