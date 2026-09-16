import pandas as pd, sys

REG = sys.argv[1] if len(sys.argv) > 1 else "northern-ca"

t = pd.read_csv(f"{REG}_partial.csv", dtype={"GEOID": str})[["GEOID", "transport_gap", "transport_defined"]]
b = pd.read_csv(f"{REG}_building_gap.csv", dtype={"GEOID": str})[["GEOID", "building_gap", "building_defined"]]
p = pd.read_csv(f"{REG}_poi_gap.csv", dtype={"GEOID": str})[["GEOID", "poi_gap", "poi_defined"]]

df = t.merge(b, on="GEOID", how="outer").merge(p, on="GEOID", how="outer")
assert df["GEOID"].str.len().eq(11).all(), "GEOID lost zero-padding in a merge"

comps = ["transport_gap", "building_gap", "poi_gap"]
defined = ["transport_defined", "building_defined", "poi_defined"]
vals = df[comps].where(df[defined].values)
df["n_defined"] = df[defined].sum(axis=1)
df["coverage_gap_score"] = vals.sum(axis=1) / df["n_defined"].clip(lower=1)
df.loc[df["n_defined"] == 0, "coverage_gap_score"] = pd.NA

print(f"{REG}: {len(df)} tracts, n_defined dist:")
print(df["n_defined"].value_counts().sort_index())
print(df["coverage_gap_score"].describe())
print("pairwise corr:")
print(df[comps].corr())

df.to_csv(f"{REG}_composite.csv", index=False)
