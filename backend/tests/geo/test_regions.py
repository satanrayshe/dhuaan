from dhuaan.geo import regions


def test_region_of():
    assert regions.region_of("North West", "Delhi") == "delhi_ncr"
    assert regions.region_of("Gurgaon", "Haryana") == "delhi_ncr"
    assert regions.region_of("Gautam Buddha Nagar", "Uttar Pradesh") == "delhi_ncr"
    assert regions.region_of("Sangrur", "Punjab") == "punjab_haryana"
    assert regions.region_of("Hisar", "Haryana") == "punjab_haryana"
    assert regions.region_of("Chandigarh", "Chandigarh") == "punjab_haryana"
    assert regions.region_of("Meerut", "Uttar Pradesh") == "_default"


def test_alpha_for_falls_back_to_pooled():
    meta = {"alpha": 0.16, "alpha_by_region": {"delhi_ncr": 6.8, "punjab_haryana": 0.15, "_default": 0.16}}
    assert regions.alpha_for(meta, "South", "Delhi") == 6.8
    assert regions.alpha_for(meta, "Sangrur", "Punjab") == 0.15
    assert regions.alpha_for(meta, "Meerut", "Uttar Pradesh") == 0.16
    assert regions.alpha_for({"alpha": 0.16}, "South", "Delhi") == 0.16
    assert regions.alpha_for(None, "South", "Delhi") == 1.0
