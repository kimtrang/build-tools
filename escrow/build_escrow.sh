#!/bin/bash -e

source ./escrow_config || exit 1

# END normal per-version configuration variables

# Compute list of platforms from Docker image names
# (will need to change this algorithm if we change the
# Docker image naming convention)
PLATFORMS=$(
  perl -e 'print join(" ", map { m@couchbasebuild/server-(.*)-build@ && $1} @ARGV)' $IMAGES
)

heading() {
  echo
  echo ::::::::::::::::::::::::::::::::::::::::::::::::::::
  echo $*
  echo ::::::::::::::::::::::::::::::::::::::::::::::::::::
  echo
}

# Top-level directory; everything to escrow goes in here.
ROOT=`pwd`
ESCROW=${ROOT}/${PRODUCT}-${VERSION}
mkdir -p ${ESCROW}

# Save copies of all Docker build images
echo "Saving Docker images..."
mkdir -p ${ESCROW}/docker_images
cd ${ESCROW}/docker_images
for img in ${IMAGES}
do
  heading "Saving Docker image ${img}"
  echo "... Pulling ${img}..."
  docker pull ${img}
  echo "... Saving local copy of ${img}..."
  output=`basename ${img}`.tar.gz
  if [ ! -s "${output}" ]
  then
    docker save ${img} | gzip > ${output}
  fi
done

# Get the source code
heading "Downloading released source code for ${PRODUCT} ${VERSION}..."
mkdir -p ${ESCROW}/src
cd ${ESCROW}/src
git config --global user.name "Couchbase Build Team"
git config --global user.email "build-team@couchbase.com"
git config --global color.ui false
#repo init -u git://github.com/couchbase/manifest -g all -m released/couchbase-server/${VERSION}.xml
repo init -u git://github.com/couchbase/manifest -g all -m ${MANIFEST_FILE}
repo sync --jobs=6

cp -rp tlm tlm_dep

# Ensure we have git history for 'master' branch of tlm, so we can
# switch to the right cbdeps build steps
( cd tlm && git fetch couchbase refs/heads/master )

# Extra tlm_dep to build depdendencies outside of tml/dep/manifest.cmake, e.g. folly's
( cd tlm_dep && git fetch couchbase refs/heads/master )

# Download all cbdeps source code
mkdir -p ${ESCROW}/deps ${ESCROW}/deps2

get_cbdep_git() {
  local dep=$1

  cd ${ESCROW}/deps
  if [ ! -d ${dep} ]
  then
    heading "Downloading cbdep ${dep} ..."
    # This special approach ensures all remote branches are brought
    # down as well, which ensures in-container-build.sh can also check
    # them out. See https://stackoverflow.com/a/37346281/1425601 .
    mkdir ${dep}
    cd ${dep}
    git clone --bare git://github.com/couchbasedeps/${dep}.git
    git config core.bare false
    git checkout
  fi
}

get_cbdep_git_folly() {
  local dep=$1

  cd ${ESCROW}/deps2
  if [ ! -d ${dep} ]
  then
    heading "Downloading cbdep ${dep} ..."
    # This special approach ensures all remote branches are brought
    # down as well, which ensures in-container-build.sh can also check
    # them out. See https://stackoverflow.com/a/37346281/1425601 .
    mkdir ${dep}
    cd ${dep}
    git clone --bare git://github.com/couchbasedeps/${dep}.git
    git config core.bare false
    git checkout
  fi
}

get_cbddeps2_src() {
  local dep=$1
  local manifest=$2

  cd ${ESCROW}/deps
  if [ ! -d ${dep} ]
  then
    mkdir ${dep}
    cd ${dep}
    heading "Downloading cbdep2 ${dep} ..."
    repo init -u git://github.com/couchbase/manifest -g all -m cbdeps/${dep}/${manifest}
    repo sync --jobs=6
  fi
}

get_cbddeps2_src_folly() {
  local dep=$1
  local manifest=$2

  cd ${ESCROW}/deps2
  if [ ! -d ${dep} ]
  then
    mkdir ${dep}
    cd ${dep}
    heading "Downloading cbdep2 ${dep} ..."
    repo init -u git://github.com/couchbase/manifest -g all -m cbdeps/${dep}/${manifest}
    repo sync --jobs=6
  fi
}

get_folly_deps() {
  grep declare ${ESCROW}/src/tlm/deps/packages/folly/CMakeLists.txt | grep -v V2| awk -F'(' '{print $2}' | awk '{print $1,$3}' > ${folly_dep_manifest}
  egrep  -A1 '^if\(WIN32\)' ${ESCROW}/src/tlm/deps/packages/folly/CMakeLists.txt | grep declare | awk -F'(' '{print $2}' | awk '{print $1,$3}' > ${ESCROW}/deps/folly.tmp
  cat ${ESCROW}/deps/folly.tmp | while read -r fl
  do
     echo == "$fl" ==
     sed -i.bak "/$fl$/d" ${folly_dep_manifest}
  done
}
get_folly_deps_v2() {
  grep declare ${ESCROW}/src/tlm/deps/packages/folly/CMakeLists.txt | grep V2 | awk -F'(' '{print $2}' | awk '{print $1 ":" $4 "-" $6}' > ${folly_dep_v2_manifest}
}

download_cbdep() {
  local dep=$1
  local ver=$2
  local dep_manifest=$3

  # skip openjdk-rt cbdeps build
  if [[ ${dep} == 'openjdk-rt' ]]
  then
    :
  else
    get_cbdep_git ${dep}
  fi

  # Split off the "version" and "build number"
  version=$(echo ${ver} | perl -nle '/^(.*?)(-cb.*)?$/ && print $1')
  cbnum=$(echo ${ver} | perl -nle '/-cb(.*)/ && print $1')

  # Figure out the tlm SHA which builds this dep
  tlmsha=$(
    cd ${ESCROW}/src/tlm &&
    git grep -c "_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})" \
      $(git rev-list --all -- deps/packages/CMakeLists.txt) \
      -- deps/packages/CMakeLists.txt \
    | awk -F: '{ print $1 }' | head -1
  )
  echo "tlmsha: cd ${ESCROW}/src/tlm && git grep -c \"_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})\" \
		git grep -c \"_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})\" \
		-- deps/packages/CMakeLists.txt \
		| awk -F: '{ print $1 }' | head -1"

  if [ -z "${tlmsha}" ]; then
    echo "ERROR: couldn't find tlm SHA for ${dep} ${version} @${cbnum}@"
    exit 1
  fi
  echo "${dep}:${tlmsha}:${ver}" >> ${dep_manifest}
}

download_cbdep_folly() {
  local dep=$1
  local ver=$2
  local dep_manifest=$3

  # skip openjdk-rt cbdeps build
  if [[ ${dep} == 'openjdk-rt' ]]
  then
    :
  else
    get_cbdep_git_folly ${dep}
  fi

  # Split off the "version" and "build number"
  version=$(echo ${ver} | perl -nle '/^(.*?)(-cb.*)?$/ && print $1')
  cbnum=$(echo ${ver} | perl -nle '/-cb(.*)/ && print $1')

  # Figure out the tlm SHA which builds this dep
  tlmsha=$(
    cd ${ESCROW}/src/tlm_dep &&
    git grep -c "_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})" \
      $(git rev-list --all -- deps/packages/CMakeLists.txt) \
      -- deps/packages/CMakeLists.txt \
    | awk -F: '{ print $1 }' | head -1
  )
  echo "tlmsha: cd ${ESCROW}/src/tlm_dep && git grep -c \"_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})\" \
    git grep -c \"_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})\" \
    -- deps/packages/CMakeLists.txt \
    | awk -F: '{ print $1 }' | head -1"

  if [ -z "${tlmsha}" ]; then
    echo "ERROR: couldn't find tlm SHA for ${dep} ${version} @${cbnum}@"
    exit 1
  fi
  echo "${dep}:${tlmsha}:${ver}" >> ${dep_manifest}
}

# Determine set of cbdeps used by this build, per platform.
for platform in ${PLATFORMS}
do
  add_packs=$(
    grep ${platform} ${ESCROW}/src/tlm/deps/manifest.cmake |grep -v V2 \
    | awk '{sub(/\(/, "", $2); print $2 ":" $4}'
  )
  add_packs_v2=$(
    grep ${platform} ${ESCROW}/src/tlm/deps/manifest.cmake | grep V2 \
    | awk '{sub(/\(/, "", $2); print $2 ":" $5 "-" $7}'
  )
  #folly_extra_deps="gflags glog"
  #gflags_extra_deps="gflags:2.2.1-cb2"
  #add_packs+=$(echo -e "\n${gflags_extra_deps}")
  echo "add_packs: $add_packs"
  echo "add_packs_v2: $add_packs_v2"
  # get folly's dependencies
  folly_dep_manifest=${ESCROW}/deps/dep_manifest_folly_${platform}.txt
  folly_dep_v2_manifest=${ESCROW}/deps/dep_manifest_folly_v2_${platform}.txt
  get_folly_deps
  for pkg in `cat ${folly_dep_manifest}`
  do
      download_cbdep_folly $(echo ${add_pack} | sed 's/:/ /g') ${folly_dep_manifest}
  done

  get_folly_deps_v2
  echo "add_packs_v2 folly: "
  $(cat $folly_dep_v2_manifest)
  # Get cbdeps V2 source
  for pkg in `cat ${folly_dep_v2_manifest}`
  do
    get_cbddeps2_src $(echo ${add_pack} | sed 's/:.*/ /g') master.xml
  done

  # Download and keep a record of all third-party deps
  dep_manifest=${ESCROW}/deps/dep_manifest_${platform}.txt
  dep_v2_manifest=${ESCROW}/deps/dep_v2_manifest_${platform}.txt
  echo "$add_packs_v2" > ${dep_v2_manifest}
  rm -f ${dep_manifest}
  for add_pack in ${add_packs}
  do
    download_cbdep $(echo ${add_pack} | sed 's/:/ /g') ${dep_manifest}
  done

  # Get cbdeps V2 source
  for add_pack in ${add_packs_v2}
  do
    get_cbddeps2_src $(echo ${add_pack} | sed 's/:.*/ /g') master.xml
  done

  ### Ensure rocksdb and folly built last
  egrep openssl ${dep_manifest} > ${ESCROW}/deps/dep_openssl.txt
  grep openssl ${ESCROW}/deps/dep_openssl.txt > ${ESCROW}/deps/dep2.txt
  egrep -v "^rocksdb|^folly" ${dep_manifest} >> ${ESCROW}/deps/dep2.txt
  egrep "^rocksdb|^folly" ${dep_manifest} >> ${ESCROW}/deps/dep2.txt
  mv ${ESCROW}/deps/dep2.txt ${dep_manifest}
done

# Need this tool for v8 build
get_cbdep_git depot_tools

# Copy in cbdep tools
for cbdep_ver in ${CBDDEPS_VERSIONS}
do
  curl -o ${ESCROW}/deps/cbdep-${cbdep_ver}-window http://packages.couchbase.com/cbdep/${cbdep_ver}/cbdep-${cbdep_ver}-window
  curl -o ${ESCROW}/deps/cbdep-${cbdep_ver}-linux http://packages.couchbase.com/cbdep/${cbdep_ver}/cbdep-${cbdep_ver}-linux
  curl -o ${ESCROW}/deps/cbdep-${cbdep_ver}-macos http://packages.couchbase.com/cbdep/${cbdep_ver}/cbdep-${cbdep_ver}-macos
  chmod +x ${ESCROW}/deps/cbdep-${cbdep_ver}-*
done

# download ~/.cbdepcache dependency
cbdep_ver_latest=$(echo ${CBDDEPS_VERSIONS} | tr ' ' '\n' | tail -1)
# Pre-populate the openjdk, openjdk-rt and analytic-jars
${ESCROW}/deps/cbdep-${cbdep_ver_latest}-linux  install -n ${ANALYTICS_JARS} ${ANALYTICS_JARS_VERSION}
${ESCROW}/deps/cbdep-${cbdep_ver_latest}-linux  install -n ${OPENJDK_NAME} ${OPENJDK_VERSION}
cp -rp /home/couchbase/.cbdepcache ${ESCROW}/deps/.cbdepcache
mkdir -p ${ESCROW}/deps/.cbdepscache
${ESCROW}/deps/cbdep-${cbdep_ver_latest}-linux  install -d ${ESCROW}/deps/.cbdepscache ${OPENJDK_RT} ${OPENJDK_RT_VERSION}

heading "Downloading Go installers..."
mkdir -p ${ESCROW}/golang
cd ${ESCROW}/golang
for gover in ${GOVERS}
do
  echo "... Go ${gover}..."
  gofile="go${gover}.linux-amd64.tar.gz"
  if [ ! -e ${gofile} ]
  then
    curl -o ${gofile} http://storage.googleapis.com/golang/${gofile}
  fi
done

heading "Copying build scripts into escrow..."
cd ${ROOT}
cp -a escrow_config templates/* ${ESCROW}
perl -pi -e "s/\@\@VERSION\@\@/${VERSION}/g; s/\@\@PLATFORMS\@\@/${PLATFORMS}/g" \
  ${ESCROW}/README.md ${ESCROW}/build-couchbase-server-from-escrow.sh

# Don't need this right now for weekly run
#heading "Creating escrow tarball (will take some time)..."
#cd ${ROOT}
#tar czf ${PRODUCT}-${VERSION}.tar.gz ${PRODUCT}-${VERSION}

heading "Done!"
