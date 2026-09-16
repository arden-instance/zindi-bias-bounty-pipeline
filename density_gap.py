import duckdb, sys, pandas as pd
from scipy.stats import spearmanr

REG = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"

con = duckdb.connect()
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
con.sql("SET s3_region='us-west-2'; SET s3_url_style='path';")
BASE = "s3://us-west-2.opendata.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge"

import numpy as np

housing = con.sql(f"""
    SELECT GEOID, housing_units, ST_Area(geometry) AS area_deg2, ST_Y(ST_Centroid(geometry)) AS lat
    FROM '{BASE}/reference/{REG}/{REG}-census-acs-housing.parquet'
""").df()
# DuckDB spatial's ST_Transform returns NULL area here (proj lookup issue), so approximate
# km^2 from raw WGS84 degree^2 area using a per-tract latitude scale factor
# (1 deg lat ~= 111.32 km; 1 deg lon ~= 111.32*cos(lat) km). Matches the cycle-285 ad hoc
# numbers to within ~0.3% when spot-checked against the saved northern-ca_density_join.csv.
housing["area_km2"] = housing["area_deg2"] * 111.32 * (111.32 * np.cos(np.radians(housing["lat"])))
housing["density"] = housing["housing_units"] / housing["area_km2"]

poi = pd.read_csv(f"{REG}_poi_gap.csv", dtype={"GEOID": str})
housing["GEOID"] = housing["GEOID"].astype(str)

df = housing.merge(poi, on="GEOID", how="inner")

fire = df[df["poi_gap_fire_defined"]]
rho_fire, p_fire = spearmanr(fire["density"], fire["poi_gap_fire"])

overall = df[df["poi_defined"]]
rho_all, p_all = spearmanr(overall["density"], overall["poi_gap"])

fire = fire.copy()
fire["tercile"] = pd.qcut(fire["density"], 3, labels=["low", "mid", "high"])
tercile_means = fire.groupby("tercile", observed=True)["poi_gap_fire"].mean()

print(f"=== {REG} ===")
print(f"n_fire_defined={len(fire)} n_poi_defined={len(overall)} n_total={len(df)}")
print(f"spearman(density, poi_gap_fire) = {rho_fire:.3f} (p={p_fire:.2e}), n={len(fire)}")
print(f"spearman(density, poi_gap)      = {rho_all:.3f} (p={p_all:.2e}), n={len(overall)}")
print("fire-gap by density tercile:")
print(tercile_means)
if tercile_means.get("high", 0) > 0:
    print(f"low/high ratio = {tercile_means['low'] / tercile_means['high']:.2f}x")

df.to_csv(f"{REG}_density_join.csv", index=False)
