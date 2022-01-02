"""
Copyright (C) 2022 Cognizant Digital Business, Evolutionary AI. All Rights Reserved.
Issued under the Academic Public License.
You can be released from the terms, and requirements of the Academic public license by purchasing a commercial license.
"""
from __future__ import absolute_import, division, print_function

import matplotlib.pyplot as plt

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import tensorflow.keras.backend as K

import pickle
import os
import time
from util import load_UCI121, dataset_read, RIO_variants_running, RIO_MRBF_running, RIO_MRBF_multiple_running
import numpy as np
from sklearn.metrics import mean_absolute_error
from scipy.special import softmax
from scipy.stats import entropy
import scipy
import trustscore

#main file to run tests for all the RIO variants on all the datasets

print(tf.__version__)

model_name = "SVGP"
#number of Epochs for NN training
EPOCHS = 1000
#number of inducing points for SVGP
M = 50

dataset_name_list = ["balance-scale", "blood", "abalone", "annealing", "car", "contrac", "mammographic", "miniboone",
                    "wine", "lenses","breast-cancer-wisc-prog","haberman-survival","post-operative","spectf","plant-texture",
                    "pima","synthetic-control","iris","breast-tissue","conn-bench-vowel-deterding","ozone","oocytes_trisopterus_states_5b",
                    "twonorm","audiology-std","heart-switzerland","musk-2","spambase","lung-cancer","molec-biol-promoter","congressional-voting",
                    "conn-bench-sonar-mines-rocks","breast-cancer-wisc-diag","thyroid","spect","optical","arrhythmia","oocytes_merluccius_nucleus_4d",
                    "credit-approval", "cylinder-bands", "energy-y1", "energy-y2", "hill-valley", "image-segmentation", "led-display", "magic",
                    "cardiotocography-3clases", "chess-krvk", "chess-krvkp", "connect-4",
                    "Phishing","messidor","Bioconcentration","Climate","yeast",
                    "adult", "bank", "cardiotocography-10clases",
                    "nursery","oocytes_trisopterus_nucleus_2f","low-res-spect","ilpd-indian-liver","statlog-image","flags","semeion",
                    "wall-following","soybean","zoo","hayes-roth","plant-margin","hepatitis","wine-quality-red","parkinsons","wine-quality-white","mushroom",
                    "monks-3","breast-cancer","pittsburg-bridges-REL-L","statlog-heart","statlog-landsat","fertility","monks-1","statlog-vehicle",
                    "vertebral-column-3clases","ionosphere","pittsburg-bridges-TYPE","acute-nephritis","libras","horse-colic","oocytes_merluccius_states_2f","breast-cancer-wisc",
                    "pittsburg-bridges-MATERIAL","statlog-shuttle","waveform","steel-plates","statlog-german-credit","trains","statlog-australian-credit",
                    "acute-inflammation","page-blocks","molec-biol-splice","seeds","titanic","ringnorm","musk-1","glass","pittsburg-bridges-T-OR-D",
                    "planning","dermatology","monks-2","ecoli","primary-tumor","waveform-noise","teaching","lymphography","balloons","heart-cleveland",
                    "pendigits","plant-shape","letter","tic-tac-toe","echocardiogram","vertebral-column-2clases","heart-va","heart-hungarian","pittsburg-bridges-SPAN"]

# For newly added datasets only
new_dataset_name_list = ["Phishing","messidor","Bioconcentration","Climate"]
new_label_name_list = ["Result", "Class", "Class", "outcome"]
new_minibatch_size_list = [1082,921,623,432]
new_num_class_list = [3,2,3,2]

new_dataset_index_dict = {}
for i in range(len(new_dataset_name_list)):
    new_dataset_index_dict[new_dataset_name_list[i]] = i


class Dropout(keras.layers.Dropout):
    """Applies Dropout to the input.
    Dropout consists in randomly setting
    a fraction `rate` of input units to 0 at each update during training time,
    which helps prevent overfitting.
    # Arguments
        rate: float between 0 and 1. Fraction of the input units to drop.
        noise_shape: 1D integer tensor representing the shape of the
            binary dropout mask that will be multiplied with the input.
            For instance, if your inputs have shape
            `(batch_size, timesteps, features)` and
            you want the dropout mask to be the same for all timesteps,
            you can use `noise_shape=(batch_size, 1, features)`.
        seed: A Python integer to use as random seed.
    # References
        - [Dropout: A Simple Way to Prevent Neural Networks from Overfitting](
           http://www.jmlr.org/papers/volume15/srivastava14a/srivastava14a.pdf)
    """
    def __init__(self, rate, training=None, noise_shape=None, seed=None, **kwargs):
        super(Dropout, self).__init__(rate, noise_shape=None, seed=None,**kwargs)
        self.training = training

    def call(self, inputs, training=None):
        if 0. < self.rate < 1.:
            noise_shape = self._get_noise_shape(inputs)

            def dropped_inputs():
                return K.dropout(inputs, self.rate, noise_shape,
                                 seed=self.seed)
            if not training:
                return K.in_train_phase(dropped_inputs, inputs, training=self.training)
            return K.in_train_phase(dropped_inputs, inputs, training=training)
        return inputs

def build_regression_model(layer_width, input_dim):
  model = keras.Sequential([
    layers.Dense(layer_width, activation=tf.nn.relu, input_shape=[input_dim]),
    layers.Dense(layer_width, activation=tf.nn.relu),
    layers.Dense(1)
  ])

  optimizer = tf.keras.optimizers.RMSprop(0.001)

  model.compile(loss='mean_squared_error',
                optimizer=optimizer,
                metrics=['mean_absolute_error', 'mean_squared_error'])
  return model

def build_classification_model(layer_width, num_class, input_dim):
  model = keras.Sequential([
    layers.Dense(layer_width, activation=tf.nn.relu, input_shape=[input_dim]),
    #layers.Dropout(rate=0.5),
    Dropout(rate=0.5, training=True),
    layers.Dense(layer_width, activation=tf.nn.relu),
    Dropout(rate=0.5, training=True),
    #layers.Dropout(rate=0.5),
    layers.Dense(num_class)
  ])

  optimizer = tf.keras.optimizers.RMSprop(0.001)

  model.compile(loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                optimizer="adam",#optimizer,
                metrics=['accuracy'])
  return model

def one_hot_encoding(origin_labels, num_class):
    one_hot_labels = np.zeros((len(origin_labels),num_class))
    one_hot_labels[np.arange(len(origin_labels)),origin_labels] = 1
    return one_hot_labels

def acc_calculate(predictions, labels):
    prediction_class = np.argmax(predictions, axis=1)
    num_correct = np.sum(prediction_class==labels)
    acc = num_correct/len(labels)
    return acc

def run_RIO_classification(framework_variant, kernel_type, M, rio_data, rio_setups, algo_spec):
    mean_list = []
    var_list = []
    correction_list = []
    NN_MAE_list = []
    RIO_MAE_list = []
    PCT_within95Interval_list = []
    PCT_within90Interval_list = []
    PCT_within68Interval_list = []
    computation_time_list = []
    hyperparameter_list = []
    num_optimizer_iter_list = []

    if algo_spec == "moderator_direct_target":
        train_labels_class = rio_data["one_hot_train_labels"][:,0].copy()
        test_labels_class = rio_data["one_hot_test_labels"][:,0].copy()
        train_NN_predictions_class = rio_data["one_hot_train_labels"][:,0].copy()
        test_NN_predictions_class = rio_data["one_hot_test_labels"][:,0].copy()
        for i in range(len(train_labels_class)):
            train_labels_class[i] = np.max(rio_data["train_NN_predictions_softmax"][i])
            train_NN_predictions_class[i] = np.max(rio_data["train_NN_predictions_softmax"][i])
            if rio_data["train_check"][i]:
                train_labels_class[i] = 1.0
            else:
                train_labels_class[i] = 0.0
        for i in range(len(test_labels_class)):
            test_labels_class[i] = np.max(rio_data["test_NN_predictions_softmax"][i])
            test_NN_predictions_class[i] = np.max(rio_data["test_NN_predictions_softmax"][i])
            if rio_data["test_check"][i]:
                test_labels_class[i] = 1.0
            else:
                test_labels_class[i] = 0.0
        train_NN_predictions_all = rio_data["train_NN_predictions_softmax"]
        test_NN_predictions_all = rio_data["test_NN_predictions_softmax"]

    NN_MAE = mean_absolute_error(test_labels_class, test_NN_predictions_class)
    if framework_variant == "GP_corrected" or framework_variant == "GP":
        with tf.Graph().as_default() as tf_graph, tf.Session(graph=tf_graph).as_default():
            MAE, PCT_within95Interval, PCT_within90Interval, PCT_within68Interval, mean, var, computation_time, hyperparameter, num_optimizer_iter, mean_train, var_train = RIO_MRBF_multiple_running(framework_variant, \
                                                                                                                                                kernel_type, \
                                                                                                                                                rio_data["normed_train_data"], \
                                                                                                                                                rio_data["normed_test_data"], \
                                                                                                                                                train_labels_class, \
                                                                                                                                                test_labels_class, \
                                                                                                                                                train_NN_predictions_class, \
                                                                                                                                                test_NN_predictions_class, \
                                                                                                                                                train_NN_predictions_all, \
                                                                                                                                                test_NN_predictions_all, \
                                                                                                                                                M, \
                                                                                                                                                rio_setups["use_ard"], \
                                                                                                                                                rio_setups["scale_array"], \
                                                                                                                                                rio_setups["separate_opt"])
    else:
        with tf.Graph().as_default() as tf_graph, tf.Session(graph=tf_graph).as_default():
            MAE, PCT_within95Interval, PCT_within90Interval, PCT_within68Interval, mean, var, computation_time, hyperparameter, num_optimizer_iter, mean_train, var_train = RIO_variants_running(framework_variant, \
                                                                                                                                                kernel_type, \
                                                                                                                                                rio_data["normed_train_data"], \
                                                                                                                                                rio_data["normed_test_data"], \
                                                                                                                                                train_labels_class, \
                                                                                                                                                test_labels_class, \
                                                                                                                                                train_NN_predictions_class, \
                                                                                                                                                test_NN_predictions_class, \
                                                                                                                                                M, \
                                                                                                                                                rio_setups["use_ard"], \
                                                                                                                                                rio_setups["scale_array"])
    if framework_variant == "GP_corrected" or framework_variant == "GP_corrected_inputOnly" or framework_variant == "GP_corrected_outputOnly" or algo_spec == "moderator_residual_target":
        correction_list.append(mean)
        mean_list.append(mean+test_NN_predictions_class)
        correction = mean.copy()
        mean = mean+test_NN_predictions_class
    else:
        mean_list.append(mean)
        correction_list.append(mean)
        correction = mean.copy()
    var_list.append(var)
    NN_MAE_list.append(NN_MAE)
    RIO_MAE_list.append(MAE)
    PCT_within95Interval_list.append(PCT_within95Interval)
    PCT_within90Interval_list.append(PCT_within90Interval)
    PCT_within68Interval_list.append(PCT_within68Interval)
    computation_time_list.append(computation_time)
    hyperparameter_list.append(hyperparameter)
    num_optimizer_iter_list.append(num_optimizer_iter)

    correction_list_transpose = np.array(correction_list).transpose()
    mean_list_transpose = np.array(mean_list).transpose()
    var_list_transpose = np.array(var_list).transpose()
    print("mean of True: {}".format(np.mean(mean[np.where(rio_data["test_check"])])))
    print("mean of False: {}".format(np.mean(mean[np.where(rio_data["test_check"] == False)])))

    exp_result = {}
    exp_result["mean"] = mean
    exp_result["var"] = var
    exp_result["RIO_MAE"] = MAE
    exp_result["PCT_within95Interval"] = PCT_within95Interval
    exp_result["PCT_within90Interval"] = PCT_within90Interval
    exp_result["PCT_within68Interval"] = PCT_within68Interval
    exp_result["computation_time"] = computation_time
    exp_result["hyperparameter"] = hyperparameter
    exp_result["num_optimizer_iter"] = num_optimizer_iter
    exp_result["test_labels"] = rio_data["test_labels"].values.reshape(-1)
    exp_result["test_NN_predictions"] = rio_data["test_NN_predictions"]
    exp_result["mean_train"] = mean_train
    exp_result["var_train"] = var_train
    exp_result["train_labels"] = rio_data["train_labels"].values.reshape(-1)
    exp_result["train_NN_predictions"] = rio_data["train_NN_predictions"]
    exp_result["mean_correct_train"] = np.mean(mean_train[np.where(rio_data["train_check"])])
    exp_result["mean_incorrect_train"] = np.mean(mean_train[np.where(rio_data["train_check"] == False)])
    exp_result["mean_correct_test"] = np.mean(mean[np.where(rio_data["test_check"])])
    exp_result["mean_incorrect_test"] = np.mean(mean[np.where(rio_data["test_check"] == False)])

    return exp_result


for dataset_index in range(len(dataset_name_list)):

    dataset_name = dataset_name_list[dataset_index]

    NN_size = "64+64"
    layer_width = 64
    RUNS = 10
    eval_iter_num = 100

    NN_info = NN_size

    if dataset_name in new_dataset_name_list:
        label_name = new_label_name_list[new_dataset_index_dict[dataset_name]]
        minibatch_size = new_minibatch_size_list[new_dataset_index_dict[dataset_name]]
        num_class = new_num_class_list[new_dataset_index_dict[dataset_name]]
        dataset = dataset_read(dataset_name)
    else:
        normed_dataset, labels = load_UCI121(dataset_name)
        num_class = np.max(labels.values)+1
        print("num_class: {}".format(num_class))

    for run in range(RUNS):
        print("run{} start".format(run))
        tf.reset_default_graph()
        with tf.Session(graph=tf.Graph()):
            # preprocess data
            if dataset_name in new_dataset_name_list:
                train_dataset = dataset.sample(frac=0.8,random_state=run)
                test_dataset = dataset.drop(train_dataset.index)
                train_labels = train_dataset.pop(label_name).astype(int)
                test_labels = test_dataset.pop(label_name).astype(int)
                train_stats = train_dataset.describe()
                train_stats = train_stats.transpose()
                normed_train_data = (train_dataset - train_stats['mean']) / train_stats['std']
                normed_test_data = (test_dataset - train_stats['mean']) / train_stats['std']
            else:
                normed_train_data = normed_dataset.sample(frac=0.8,random_state=run)
                normed_test_data = normed_dataset.drop(normed_train_data.index)
                train_labels = labels.take(normed_train_data.index)
                test_labels = labels.drop(normed_train_data.index)
            minibatch_size = len(normed_train_data)

            time_checkpoint1 = time.time()

            # training NN
            model = build_classification_model(layer_width, num_class, len(normed_train_data.keys()))

            # The patience parameter is the amount of epochs to check for improvement
            early_stop = keras.callbacks.EarlyStopping(monitor='val_loss', patience=50)

            history = model.fit(normed_train_data, train_labels, epochs=EPOCHS,
                                validation_split = 0.2, verbose=2, callbacks=[early_stop])
            time_checkpoint2 = time.time()

            loss, NN_acc = model.evaluate(normed_test_data, test_labels, verbose=0)
            print("computation_time_NN: {}".format(time_checkpoint2-time_checkpoint1))
            print("Testing set accuracy: {}".format(NN_acc))

            probability_model = tf.keras.Sequential([model, tf.keras.layers.Softmax()])

            test_NN_predictions_softmax_list = []
            train_NN_predictions_softmax_list = []
            test_NN_predictions_list = []
            train_NN_predictions_list = []
            for eval_iter in range(eval_iter_num):
                test_NN_predictions_softmax = probability_model.predict(normed_test_data)
                train_NN_predictions_softmax = probability_model.predict(normed_train_data)
                test_NN_predictions = model.predict(normed_test_data)
                train_NN_predictions = model.predict(normed_train_data)
                test_NN_predictions_softmax_list.append(test_NN_predictions_softmax)
                train_NN_predictions_softmax_list.append(train_NN_predictions_softmax)
                test_NN_predictions_list.append(test_NN_predictions)
                train_NN_predictions_list.append(train_NN_predictions)
                #print("iteration {}".format(eval_iter))
                #print(test_NN_predictions_softmax[:10])
                #print(train_NN_predictions_softmax[:10])
                #print(test_NN_predictions[:10])
                #print(train_NN_predictions[:10])
            #print(test_NN_predictions_softmax_list)
            test_NN_predictions_softmax_mean = np.mean(test_NN_predictions_softmax_list, axis=0)
            #print(test_NN_predictions_softmax_mean)
            train_NN_predictions_softmax_mean = np.mean(train_NN_predictions_softmax_list, axis=0)
            test_NN_predictions_entropy = entropy(test_NN_predictions_softmax_mean, axis=-1)
            train_NN_predictions_entropy = entropy(train_NN_predictions_softmax_mean, axis=-1)
            #print(test_NN_predictions_entropy.shape)
            #print(test_NN_predictions_entropy)
            exp_info = {}
            exp_info["test_NN_predictions_list"] = test_NN_predictions_list
            exp_info["train_NN_predictions_list"] = train_NN_predictions_list
            exp_info["test_NN_predictions_entropy"] = test_NN_predictions_entropy
            exp_info["train_NN_predictions_entropy"] = train_NN_predictions_entropy
            result_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)),'Results','{}_exp_info_dropout_{}_run{}.pkl'.format(dataset_name, NN_info, run))
            with open(result_file_name, 'wb') as result_file:
                pickle.dump(exp_info, result_file)
