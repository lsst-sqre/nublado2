#!/bin/bash -ex
helm delete --purge n2-dev || true
docker build -t lsstsqre/nublado2:dev .
helm upgrade --install n2-dev nublado2 --namespace n2-dev --values dev-values.yaml
