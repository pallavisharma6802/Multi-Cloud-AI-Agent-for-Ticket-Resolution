# Standalone Grafana image for hosts (e.g. Render) that can't bind-mount
# repo folders like docker-compose.yml does locally. Bakes dashboards and
# provisioning in at build time instead.
FROM grafana/grafana-oss:11.3.0

# Baked in at build time, not via GF_INSTALL_PLUGINS -- that env var makes
# the entrypoint re-download and reinstall the plugin on every container
# boot, which raced with SQLite migrations on Render's free tier and
# produced "database is locked" errors that silently blocked dashboard
# provisioning (folder/dashboard creation failed, so /api/search came back
# empty even though the container reported healthy).
RUN grafana-cli --pluginsDir "/var/lib/grafana/plugins" plugins install grafana-bigquery-datasource 2.2.1

COPY provisioning/ /etc/grafana/provisioning/
COPY dashboards/ /var/lib/grafana/dashboards/
