# Installation

The original installation mentioned DyNet `2.1`, but used `2.0.3` in the code
examples. `2.0.3` *did not* work, so
I installed DyNet 2.1 from [source][1], as well as the specific version of
Eigen linked there.

The next step was to create a conda environment with `python==3.7.9` as
in the `open-sesame` instructions and then install:

    pip install cython numpy

`cython` for the build-from-source, and `numpy` to provide the correct version
of numpy for DyNet, which otherwise tries to install an incorrect version.

Ensure the DyNet build is done with the conda version of python.

# Data preprocessing

    git clone https://github.com/swabhs/open-sesame.git

 - Downloaded [FrameNet version 1.7][2]
 - GloVe link in repo broken, [located][3] and downloaded

    python -m sesame.preprocess

# Memory

By default, DyNet requests only 512 MB of RAM. Not sure if that's the
bottleneck, but you can ask for more:

    import dynet_config
    dynet_config.set(mem=12000)

`mem=` is in MB, so this ~12 GB of RAM.

Run this before the `from dynet import ...` command.
I tried this with `targetid.py` but it didn't show an appreciable speed-up
(~30 min).

# Training

For each model `target frame arg`:

python \
    -m sesame.${i}id                        \
    --mode          train                   \
    --model_name    fn1.7-pretrained-${i}id
    done

## Training time

 - `target`: 30 min on 4x16gb
 - `frame`:  7 h, 23 min on 1 core, 8 GB RAM (not given more than default
                512 MB of RAM).
 - `arg`:

## Training models

Models are uploaded to [Box][4].

[1]: https://github.com/clab/dynet/releases/tag/2.1
[2]: https://drive.google.com/open?id=1s4SDt_yDhT8qFs1MZJbeFf-XeiNPNnx7
[3]: https://nlp.stanford.edu/projects/glove/
[4]: https://umn.box.com/s/eru3a30ejulpzfiqklue83buv9fh54hm
