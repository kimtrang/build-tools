#!/bin/bash -e

TOP=${WORKSPACE}
platform=centos7
mkdir -p $TOP/thirdparty-src
git clone git://github.com/couchbase/tlm.git

mkdir -p $TOP/thirdparty-src/deps

heading() {
  echo
  echo ::::::::::::::::::::::::::::::::::::::::::::::::::::
  echo $*
  echo ::::::::::::::::::::::::::::::::::::::::::::::::::::
  echo
}

get_cbdep_git() {
  local dep=$1
  local git_branch=$2

  cd $TOP/thirdparty-src/deps
  if [ ! -d ${dep} ]
  then
    heading "Downloading cbdep ${dep} ..."
    git clone git://github.com/couchbasedeps/${dep}.git
    cd ${dep}
    git checkout ${git_branch}
  fi
}

get_build_manifests_repo() {
  cd $TOP
  heading "Downloading build-manifests ..."
  rm -rf build-manifests
  git clone git://github.com/couchbase/build-manifests.git

}

get_cbddeps2_src() {
  local dep=$1
  local ver=$2
  local manifest=$3
  local sha=$4

  cd $TOP/thirdparty-src/deps
  if [ ! -d ${dep} ]
  then
    mkdir ${dep}
    cd ${dep}
    heading "Downloading cbdep2 ${manifest} at ${sha} ..."
    repo init -u git://github.com/couchbase/build-manifests -g all -m cbdeps/${manifest} -b ${sha}
    repo sync --jobs=6
  fi
}

download_cbdep() {
  local dep=$1
  local ver=$2
  local dep_manifest=$3

  # Split off the "version" and "build number"
  version=$(echo ${ver} | perl -nle '/^(.*?)(-cb.*)?$/ && print $1')
  cbnum=$(echo ${ver} | perl -nle '/-cb(.*)/ && print $1')

  # Figure out the tlm SHA which builds this dep
  tlmsha=$(
    cd ${TOP}/tlm &&
    git grep -c "_ADD_DEP_PACKAGE(${dep} ${version} .* ${cbnum})" \
      $(git rev-list --all -- deps/packages/CMakeLists.txt) \
      -- deps/packages/CMakeLists.txt \
    | awk -F: '{ print $1 }' | head -1
  )
  if [ -z "${tlmsha}" ]; then
    echo "ERROR: couldn't find tlm SHA for ${dep} ${version} @${cbnum}@"
    exit 1
  fi
  echo "${dep}:${tlmsha}:${ver}" >> ${dep_manifest}

  # Logic to get the tag/branch version of dep
  cd ${TOP}/tlm
  git reset --hard
  git clean -dfx
  git checkout ${tlmsha}
  dep_git_branch=$(grep "_ADD_DEP_PACKAGE(${dep}"  deps/packages/CMakeLists.txt  | sed 's/(/ /g' | awk '{print $4}')

  echo
  echo "dep: $dep == ver: $ver == tlmsha: $tlmsha == dep_git_branch:$dep_git_branch"
  echo

  # skip openjdk-rt cbdeps build
  if [[ ${dep} == 'openjdk-rt' ]]
  then
    :
  else
    get_cbdep_git ${dep} ${dep_git_branch} || exit 1
  fi
}

add_packs=$(
  grep ${platform} ${TOP}/tlm/deps/packages/folly/CMakeLists.txt  |grep -v V2 \
  | awk '{sub(/\(/, "", $2); print $2 ":" $4}';
  grep ${platform} ${TOP}/tlm/deps/manifest.cmake |grep -v V2 \
  | awk '{sub(/\(/, "", $2); print $2 ":" $4}'
)
add_packs_v2=$(
  grep ${platform} ${TOP}/tlm/deps/packages/folly/CMakeLists.txt  | grep V2 \
  | awk '{sub(/\(/, "", $2); print $2 ":" $5 "-" $7}';
  grep ${platform} ${TOP}/tlm/deps/manifest.cmake | grep V2 \
  | awk '{sub(/\(/, "", $2); print $2 ":" $5 "-" $7}'
)
echo "add_packs: $add_packs"
echo
echo "add_packs_v2: $add_packs_v2"

# Download and keep a record of all third-party deps
dep_manifest=$TOP/thirdparty-src/deps/dep_manifest_${platform}.txt
dep_v2_manifest=${TOP}/thirdparty-src/deps/dep_v2_manifest_${platform}.txt
echo "$add_packs_v2" > ${dep_v2_manifest}
rm -f ${dep_manifest}

# Get cbdeps V2 source first
get_build_manifests_repo
for add_pack in ${add_packs_v2}
do
  dep=$(echo ${add_pack} | sed 's/:/ /g' | awk '{print $1}') # zlib
  ver=$(echo ${add_pack} | sed 's/:/ /g' | awk '{print $2}' | sed 's/-/ /' | awk '{print $1}') # 1.2.11
  bldnum=$(echo ${add_pack} | sed 's/:/ /g' | awk '{print $2}' | sed 's/-/ /' | awk '{print $2}')
  pushd ${TOP}/build-manifests/cbdeps
  sha=$(git log --pretty=oneline ${dep}/${ver}/${ver}.xml  |grep ${ver}-${bldnum} | awk '{print $1}')
  echo "dep: $dep == ver: $ver == sha: $sha == manifest: ${dep}/${ver}/${ver}.xml"
  get_cbddeps2_src ${dep} ${ver} ${dep}/${ver}/${ver}.xml ${sha} || exit 1
done

# Get cbdep after V2 source
for add_pack in ${add_packs}
do
  download_cbdep $(echo ${add_pack} | sed 's/:/ /g') ${dep_manifest} || exit 1
done

# sort -u to remove redundant cbdeps
cat ${dep_manifest} | sort -u > dep_manifest.tmp
mv dep_manifest.tmp ${dep_manifest}
cat ${dep_v2_manifest} | sort -u > dep_v2_manifest.tmp
mv dep_v2_manifest.tmp ${dep_v2_manifest}

# Need this tool for v8 build
#get_cbdep_git depot_tools

# Removed all .git and .repo
find . -type d -name .repo -or -name .git | xargs rm -rf
