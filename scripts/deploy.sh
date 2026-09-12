#!/usr/bin/env bash
# Build, upload, invalidate. Touches nothing outside the fx-table stack.
#
#   scripts/deploy.sh            build + upload + invalidate (refuses while the page is incomplete)
#   scripts/deploy.sh --preview  ship a build that still carries owner placeholders, on purpose
#   scripts/deploy.sh --infra    also run `sam build && sam deploy` first
set -euo pipefail

cd "$(dirname "$0")/.."

STACK=fx-table
REGION=eu-central-1

# The readiness gate exists so that publishing an incomplete page is a deliberate, visible act
# rather than the default. --preview is that act, and it says so in the output.
PREVIEW=0
for arg in "$@"; do [[ "$arg" == "--preview" ]] && PREVIEW=1; done

if [[ "${1:-}" == "--infra" ]]; then
  ( cd infra && sam build --template-file template.yaml >/dev/null && sam deploy --no-confirm-changeset --no-fail-on-empty-changeset )
fi

read -r BUCKET DIST <<<"$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'||OutputKey=='DistributionId'].OutputValue" \
  --output text | tr '\t' ' ')"

# describe-stacks does not promise output order; sort it out by shape
if [[ "$BUCKET" == E* && "$BUCKET" != fx-* ]]; then TMP="$BUCKET"; BUCKET="$DIST"; DIST="$TMP"; fi

echo "bucket=$BUCKET  distribution=$DIST"

if [[ "$PREVIEW" == "1" ]]; then
  echo "PREVIEW DEPLOY: readiness gate skipped on purpose."
  echo "Anything listed below as 'OWNER MUST SUPPLY' goes live as a visible marker."
  python build.py
else
  # --production refuses to build while an owner fact or a real asset is missing, and removes dist/
  # so a stale preview build can never be uploaded by the sync below.
  python build.py --production
fi

# hashed/immutable assets first, long cache
# No --delete: asset names are content-hashed, so the previous set is orphaned, not replaced.
# Keeping it addressable covers the seconds between this upload and the invalidation, when an edge
# may still serve HTML pointing at the old names, and makes a rollback a plain re-deploy.
# Prune later with: aws s3 sync dist/assets "s3://$BUCKET/assets" --delete --dryrun
aws s3 sync dist/assets "s3://$BUCKET/assets" \
  --cache-control "public, max-age=31536000, immutable" --only-show-errors

# html: always revalidate, so a deploy is visible immediately.
# Every file under assets/ carries a content hash in its name (build.py), which is what makes the
# immutable cache-control above honest: a changed asset is a new URL and stale HTML can never point at it.
aws s3 sync dist "s3://$BUCKET" --delete --exclude "assets/*" \
  --cache-control "public, max-age=0, must-revalidate" \
  --content-type "text/html; charset=utf-8" --exclude "*.txt" --exclude "*.xml" --exclude "*.json" --only-show-errors

aws s3 cp dist/robots.txt "s3://$BUCKET/robots.txt" \
  --cache-control "public, max-age=3600" --content-type "text/plain; charset=utf-8" --only-show-errors
aws s3 cp dist/sitemap.xml "s3://$BUCKET/sitemap.xml" \
  --cache-control "public, max-age=3600" --content-type "application/xml; charset=utf-8" --only-show-errors

# fonts and images need their real types back (the html sync above is type-blind)
for f in dist/assets/fonts/*.woff2; do
  aws s3 cp "$f" "s3://$BUCKET/assets/fonts/$(basename "$f")" \
    --cache-control "public, max-age=31536000, immutable" --content-type "font/woff2" --only-show-errors
done

aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --query 'Invalidation.Id' --output text
echo "deployed https://table.central-aparts.store"
