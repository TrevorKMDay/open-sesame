#!/bin/bash

#SBATCH --time=12:00:00
#SBATCH --mem=8GB
#SBATCH --gres=gpu:v100:1
#SBATCH -p v100

MODEL=${1}

#conda init bash
#conda activate srl

python -m sesame.${MODEL}id     \
    --mode refresh              \
    --model_name "fn1.0-pretrained-${MODEL}id"
