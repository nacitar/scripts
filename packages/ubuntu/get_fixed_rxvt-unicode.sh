#!/bin/bash

PATCH_DIR="$(readlink -f "$(dirname "$0")")"

die() {
  echo "$@" 1>&2
  exit 1
}

PACKAGE="rxvt-unicode-256color"
PACKAGE_NAME="rxvt-unicode"

echo "Be sure that you ran: sudo apt-get build-dep $PACKAGE"
sleep 5

[ -d "build" ] && rm -rf build
mkdir build && pushd build || die "Couldn't enter build directory"

# get the source
apt-get source "$PACKAGE" && pushd "$PACKAGE_NAME"-* || die "Couldn't enter source folder."

# apply patches
failures=0

shopt -s nullglob
for filename in "$PATCH_DIR/$PACKAGE/"*.patch; do
  applied=0
  for level in 0 1; do
    # if the dry run fails, try the next patchlevel, otherwise apply it
    patch -p$level --dry-run -s -f -i "$filename" &>/dev/null || continue
    patch -p$level -i "$filename" && applied=1
    break
  done
  if [ $applied -ne 1 ]; then
    echo "Failed to apply patch: $filename"
    failures=$(($failures + 1))
  fi
done
shopt -u nullglob
echo "OUTPUT: $PWD"
if [ $failures -ne 0 ]; then
  echo "ERRORS OCCURRED: $failures files failed."
  exit $failures
fi
if [ $# -ne 0 ]; then
  echo "Command line arguments found; setting configure overrides to match: '$@'"
  sed -i "s/^\(cfgoverride = \).*$/\1$@/" debian/rules || die "Failed to set overrides."
fi

# Build the package itself
dpkg-buildpackage -b -uc -us || die "Failed to build the package!"

# Leave source folder
popd

# Parenthesis to force glob expansion
output_file=(*"$PACKAGE"*.deb)
[ -r "$output_file" ] || die "Couldn't identify the output deb file! $PWD and
$output_file"

# Leave build folder
popd

mv build/"$output_file" . || die "Couldn't move package out of build folder."
rm -rf build

echo "Install by running: sudo dpkg -i \"$output_file\""
