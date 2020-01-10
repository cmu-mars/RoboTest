#!/bin/sh

/home/haskell/cmur --thPort 5001 \
  --shellApi http://nevermind:8080 \
  --taApi http://cp1_ta:5000/ \
  --parameters '{"baselineFlag": "ActualTest", "testId": {"uuid": "d90fd3c2-063e-4e64-84e5-ca0c5f1a34cd"}, "cp": "CP1", "testGrpId": "2bb64082-900c-4846-9f0c-32bdc7a91132", "params": {"pert_batt": null,   "pert_placeObs": { "x": -19.08, "y": 11.08}, "cp1Init": {"target-locs": ["l2","l4","l5"], "start-loc": "l1", "discharge-budget": 10, "power-model": 0, "level": "c"}}, "tcId": 0}'