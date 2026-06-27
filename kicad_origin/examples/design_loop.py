    sp = None
    if spread:
        sp = spread_placement(b)
        _save(b, work)
        if kcli:
            stages.append({"stage": "spread(拉开后)", **real_drc(kcli, work),
                           "moved": sp.moved,
                           "overlaps": f"{sp.overlaps_before}→{sp.overlaps_after}"})

    nets = dna.nets