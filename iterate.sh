#!/bin/bash -ex
if [ -f dev-chart.tgz ]
then
  CHART=dev-chart.tgz
else
  CHART=lsst-sqre/nublado2
fi

helm delete nublado2 --namespace nublado2 || true
docker build -t lsstsqre/nublado2:dev .
helm upgrade --install nublado2 $CHART --namespace nublado2 --values dev-values.yaml --create-namespace
