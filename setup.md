# Installation

    pip install dynet==2.0.3

 - Manually installed latest Eigen from GitLab

    pip install nltk==3.5
    python -m nltk.downloader averaged_perceptron_tagger wordnet

# Data preprocessing

    git clone https://github.com/swabhs/open-sesame.git

 - Downloaded [FrameNet version 1.7](1)
 - GloVe link in repo broken,
    [located](https://nlp.stanford.edu/projects/glove/) and downloaded

    python -m sesame.preprocess

1: https://drive.google.com/open?id=1s4SDt_yDhT8qFs1MZJbeFf-XeiNPNnx7

# Training

Not literally in a for loop, but three-step training process. It self-allocates
512MB of memory

    for i in target frame arg ; do
        python -m sesame.${i}id \
            --mode train --model_name fn1.7-pretrained-${i}id
    done

 - `target`: 30 min on 4x16gb
 - `frame`:
 - `arg`: