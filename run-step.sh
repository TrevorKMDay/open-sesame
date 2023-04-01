#!/bin/bash 

#SBATCH --time=12:00:00
#SBATCH --mem=8GB

MODEL=${1}

python -m sesame.${MODEL}id --mode train --model_name "fn1.0-pretrained-${MODEL}id"
