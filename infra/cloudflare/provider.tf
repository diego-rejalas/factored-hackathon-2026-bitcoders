# The token comes from the environment (CLOUDFLARE_API_TOKEN), never from a file. It needs, on this account and zone:
# Pages Edit, R2 Edit (the bucket and its public address), and DNS Edit.
provider "cloudflare" {}
