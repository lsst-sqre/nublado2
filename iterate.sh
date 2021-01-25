#!/bin/bash -ex
if [ -f dev-chart.tgz ]
then
  CHART=dev-chart.tgz
else
  CHART=cachemachine
fi

helm delete --purge n2-dev || true
docker build -t lsstsqre/nublado2:dev .
helm upgrade --install n2-dev $CHART --namespace n2-dev --values dev-values.yaml --create-namespace
