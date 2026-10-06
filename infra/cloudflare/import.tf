# One-time adoption of what was created by hand before this existed. Terraform reads these on the first plan, shows them as
# imports, and puts them in the state on the first apply. Once that apply has run, delete this file in a follow-up change.
#
# The managed domain has no import: it is enabled by the resource itself, which is idempotent for a bucket that already has it.

import {
  to = cloudflare_pages_project.landing
  id = "${var.account_id}/${var.pages_project_name}"
}

import {
  to = cloudflare_r2_bucket.media
  id = "${var.account_id}/${var.r2_bucket_name}/default"
}

import {
  to = cloudflare_dns_record.app
  id = "${var.zone_id}/${var.app_record_id}"
}
