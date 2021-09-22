import copy
import os
from pathlib import Path

import torch
import torch.nn as nn
import pandas as pd
import numpy as np

import ai_based.data_handling.ai_datasets as ai_datasets
import ai_based.utilities.evaluators
from ai_based.networks import MLP, Cnn1D
from ai_based.training.experiment import Experiment
from util.datasets import SlidingWindowDataset, GroundTruthClass
from util.paths import DATA_PATH
from util.subfolder_split import split_subfolder_list


np.seterr(all='raise')


experiment_config = {
    "name": f"test-experiment",
    "target_device": torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu"),
    "init_weights_path": None,
    "checkpointing_enabled": True,
    "checkpointing_cyclic_epoch": 10,  # May be None. If set, we automatically take a checkpoint every N epochs.
    "n_repetitions": 1,
    "deterministic_mode": False
}
print(f"Target device: {experiment_config['target_device']}")


sliding_window_dataset_config = SlidingWindowDataset.Config(
    downsample_frequency_hz=5,
    time_window_size=pd.to_timedelta("5 minutes"),
    time_window_stride=1,  # 1
    ground_truth_vector_width=11
)

data_folder = Path("~/Physionet2018/physionet.org/files/challenge-2018/1.0.0/training")
# data_folder = DATA_PATH / "training"
train_folders, test_folders = split_subfolder_list(folder=data_folder, split_ratio=0.7)

training_dataset_config = ai_datasets.AiDataset.Config(
    sliding_window_dataset_config=sliding_window_dataset_config,
    dataset_folders=train_folders,
    noise_mean_std=(0, 0.4)
)
test_dataset_config = ai_datasets.AiDataset.Config(
    sliding_window_dataset_config=sliding_window_dataset_config,
    dataset_folders=test_folders,
    noise_mean_std=(0, 0.4),
)

# Pull some knowledge out of our train data set
train_dataset = ai_datasets.AiDataset(config=training_dataset_config, progress_message="Loading train dataset samples")
test_dataset = ai_datasets.AiDataset(config=test_dataset_config, progress_message="Loading test dataset samples")
features_shape, gt_shape = train_dataset[0][0].shape, train_dataset[0][1].shape

class_occurrences_train = train_dataset.get_gt_class_occurrences()
class_occurrences_test = test_dataset.get_gt_class_occurrences()
class_weights = [1 / class_occurrences_train[klass] for klass in class_occurrences_train.keys()]
class_weights = torch.FloatTensor(class_weights)


trainer_config = {
    "num_epochs": 40,
    "batch_size": 1024,  # 128,
    "batch_size_test": 2048,  # May be None
    "determine_train_dataset_performance": False,  # Do we wish to determine model performance also _over train dataset at the end of each epoch? This, of course, takes time!
    "logging_frequency": 1,
    "log_loss": True,
    "log_grad": False,
    "verbose": False,
    "num_loading_workers": len(os.sched_getaffinity(0)) - 2,
    "evaluator_type": ai_based.utilities.evaluators.ConfusionMatrixEvaluator,
    "interest_keys": [],  # Should stay empty, as used by analysis tools in later step
}

base_hyperparameters = {
    "loss_function": torch.nn.CrossEntropyLoss(weight=class_weights),
    "optimizer": torch.optim.Adam,
    "optimizer_args": {
        "betas": [0.9, 0.999],
        "eps": 1e-08,
        "lr": 5e-4,  # 5e-4    It is common to grid search learning rates on a log scale from 0.1 to 10^-5 or 10^-6
        "weight_decay": 1e-3  # 5e-3
    },
    "scheduler": torch.optim.lr_scheduler.ReduceLROnPlateau,
    "scheduler_requires_metric": True,
    "scheduler_args": {
        "mode": "min",
        "factor": 0.333,
        "patience": 1,
        "verbose": True
    },
    "train_dataset": train_dataset,
    "test_dataset": test_dataset,
    "dataset_type": None,  # ai_datasets.AiDataset,
    "train_dataset_config": None,  # training_dataset_config,
    "test_dataset_config": None,  # test_dataset_config,
    "model": MLP,
    "model_config": MLP.Config(
        input_tensor_shape=features_shape,
        output_tensor_shape=(len(GroundTruthClass), *gt_shape),
        hidden_layer_configs=[
           MLP.Config.HiddenLayerConfig(out_features=10000, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
           MLP.Config.HiddenLayerConfig(out_features=3000, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
           MLP.Config.HiddenLayerConfig(out_features=1000, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
           MLP.Config.HiddenLayerConfig(out_features=300, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
           MLP.Config.HiddenLayerConfig(out_features=100, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
        ],
        last_layer_dropout=0.6,
        last_layer_use_batchnorm=True
    ),
    # "model": Cnn1D,
    # "model_config": Cnn1D.Config(
    #     input_tensor_shape=input_data_shape,
    #     output_tensor_shape=(3,),
    #     encoder_layer_configs=[
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=64, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=64, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=128, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=128, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=256, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=256, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.3, activation_fn=nn.ReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=256, kernel_size=11, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.3, activation_fn=nn.ReLU()),
    #     ],
    #     hidden_dense_layer_configs=[
    #         MLP.Config.HiddenLayerConfig(out_features=1000, use_batchnorm=True, dropout=0.3, activation_fn=nn.ReLU()),
    #         MLP.Config.HiddenLayerConfig(out_features=300, use_batchnorm=True, dropout=0.3, activation_fn=nn.ReLU()),
    #         MLP.Config.HiddenLayerConfig(out_features=30, use_batchnorm=True, dropout=0.3, activation_fn=nn.ReLU()),
    #     ],
    #     last_layer_dropout=0.3,
    #     last_layer_use_batchnorm=True
    # )
    # "model": CompositionNet,
    # "model_config": CompositionNet.Config(
    #     input_tensor_shape=input_data_shape,
    #     output_tensor_shape=(3,),
    #     convolutional_layer_configs=[
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=32, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=32, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=64, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=64, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=64, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=128, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=None, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #         Cnn1D.Config.EncoderLayerConfig(out_channels=128, kernel_size=7, stride=1, use_batchnorm=True, pool_factor=3, dropout=0.2, activation_fn=nn.LeakyReLU()),
    #     ],
    #     hidden_dense_layer_configs=[
    #         MLP.Config.HiddenLayerConfig(out_features=1000, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
    #         MLP.Config.HiddenLayerConfig(out_features=300, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
    #         MLP.Config.HiddenLayerConfig(out_features=100, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
    #         MLP.Config.HiddenLayerConfig(out_features=30, use_batchnorm=True, dropout=0.8, activation_fn=nn.LeakyReLU()),
    #     ],
    #     last_layer_dropout=0.6,
    #     last_layer_use_batchnorm=True
    # )
}


def main():
    print(f"Training dataset:\n"
          f"  - class occurrences: {class_occurrences_train}\n"
          f"  - resulting (vanilla) class weights: {class_weights}\n"
          f"\n"
          f"Test dataset:\n"
          f"  - class occurrences: {class_occurrences_test}\n"
          f"\n"
          f"Input features shape:  {features_shape}\n"
          f"  Ground truth shape:  {gt_shape}")
    print()

    Experiment.SILENTLY_OVERWRITE_PREVIOUS_RESULTS = True
    experiment = Experiment(experiment_config, trainer_config, base_hyperparameters)

    experiment.run()


if __name__ == "__main__":
    main()
