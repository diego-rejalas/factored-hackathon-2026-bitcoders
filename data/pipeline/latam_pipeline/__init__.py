"""LATAM Bank pipeline as independent stages.

Each stage opens and closes its own DuckDB connection, so it can run as its own Airflow task
(or as one step of the Cloud Run job) without sharing a process. The stages hand over through
the DuckDB file at `Settings.db_path`.
"""
