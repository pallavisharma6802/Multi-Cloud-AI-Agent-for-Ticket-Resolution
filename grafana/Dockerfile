# Standalone Grafana image for hosts (e.g. Render) that can't bind-mount
# repo folders like docker-compose.yml does locally. Bakes dashboards and
# provisioning in at build time instead.
FROM grafana/grafana-oss:11.3.0

ENV GF_INSTALL_PLUGINS="grafana-bigquery-datasource 2.2.1"

COPY provisioning/ /etc/grafana/provisioning/
COPY dashboards/ /var/lib/grafana/dashboards/
