#!/bin/bash

module load cmake

# See install materials here:
#   https://dynet.readthedocs.io/en/latest/python.html
#   (but this uses bitbucket eigen, which is no longer available)

python -m pip install cython numpy

cd /home/elisonj/day00096/dynet-base || exit

# getting dynet
if [ ! -d dynet ] ; then
    echo "Cloning DyNet"

    # wget -nc https://github.com/clab/dynet/archive/refs/tags/2.0.3.zip
    wget -nc https://github.com/clab/dynet/archive/refs/tags/2.1.zip

    # unzip -n 2.0.3.zip
    unzip -n 2.1.zip

    # ln -s "dynet-2.0.3" "dynet"
    ln -s dynet-2.1 dynet
fi

# exit

# eigen
# Manually downloaded stable release 3.4.0
#   https://gitlab.com/libeigen/eigen/-/tags

# See instructions here: https://pypi.org/project/dyNET/
# Version 2.1.0
ezip=https://github.com/clab/dynet/releases/download/2.1/eigen-b2e267dc99d4.zip
mkdir -p eigen
cd eigen || exit
wget -nc ${ezip}
unzip -n eigen-b2e267dc99d4.zip
cd ..

cd dynet || exit
mkdir -p build
cd build || exit

# WITHOUT GPU support
PYTHON=$(which python)
cmake .. -DEIGEN3_INCLUDE_DIR=../../eigen -DPYTHON="${PYTHON}"

PATH_TO_DYNET=${HOME}/dynet-base/dynet/
PATH_TO_EIGEN=${HOME}/dynet-base/eigen/

make -j 3

cd python || exit
${PYTHON}  ../../setup.py build --build-dir=.. --skip-build install --user