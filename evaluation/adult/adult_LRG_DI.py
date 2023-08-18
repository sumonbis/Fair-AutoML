# -*- encoding: utf-8 -*-
"""
=======
Metrics
=======

*Auto-sklearn* supports various built-in metrics, which can be found in the
:ref:`metrics section in the API <api:Built-in Metrics>`. However, it is also
possible to define your own metric and use it to fit and evaluate your model.
The following examples show how to use built-in and self-defined metrics for a
classification problem.
"""

from ConfigSpace.configuration_space import ConfigurationSpace
from ConfigSpace.hyperparameters import CategoricalHyperparameter, UniformFloatHyperparameter, \
    UniformIntegerHyperparameter
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

import autosklearn.pipeline.components.classification
from autosklearn.pipeline.components.classification \
    import AutoSklearnClassificationAlgorithm
from autosklearn.pipeline.constants import DENSE, UNSIGNED_DATA, PREDICTIONS, SPARSE, SIGNED_DATA
import datetime
import json

import PipelineProfiler

import pickle
import shutil

import math
from sklearn.ensemble import RandomForestClassifier

import autosklearn.classification
import autosklearn.metrics
import warnings

warnings.filterwarnings('ignore')
from aif360.datasets import AdultDataset
from sklearn.preprocessing import StandardScaler
import os
import numpy as np

import sklearn.metrics
import autosklearn.classification
from autosklearn.upgrade.metric import disparate_impact, statistical_parity_difference, equal_opportunity_difference, \
    average_odds_difference
from autosklearn.Fairea.utility import get_data, write_to_file
from autosklearn.Fairea.fairea import create_baseline, normalize, get_classifier, classify_region, compute_area

train_list = "data_orig_train_adult.pkl"
test_list = "data_orig_test_adult.pkl"
def custom_preprocessing(df):
    def group_race(x):
        if x == "White":
            return 1.0
        else:
            return 0.0

    # Recode sex and race
    df['sex'] = df['sex'].replace({'Female': 0.0, 'Male': 1.0})
    df['race'] = df['race'].apply(lambda x: group_race(x))
    return df


############################################################################
# File Remover
# ============
import shutil

now = str(datetime.datetime.now())[:19]
now = now.replace(":", "_")
temp_path = "adult_lrg_di" + str(now)
try:
    os.remove("test_split.txt")
except:
    pass
try:
    os.remove("num_keys.txt")
except:
    pass
try:
    os.remove("beta.txt")
except:
    pass

f = open("beta.txt", "w")
f.close()

############################################################################
# Data Loading
# ============
import pandas as pd
from aif360.datasets import GermanDataset, StandardDataset

train = pd.read_pickle(train_list)
test = pd.read_pickle(test_list)
na_values=['?']
default_mappings = {
    'label_maps': [{1.0: '>50K', 0.0: '<=50K'}],
    'protected_attribute_maps': [{1.0: 'White', 0.0: 'Non-white'},
                                 {1.0: 'Male', 0.0: 'Female'}]
}



data_orig_train = StandardDataset(df=train, label_name='income-per-year',
            favorable_classes=['>50K', '>50K.'],
            protected_attribute_names=['race'],
            privileged_classes=[[1]],
            instance_weights_name=None,
            categorical_features=['workclass', 'education', 'marital-status', 'occupation',
                                                  'relationship', 'native-country'],
            features_to_keep=[],
            features_to_drop=['income', 'native-country', 'hours-per-week'], na_values=na_values,
            custom_preprocessing=custom_preprocessing, metadata=default_mappings)
data_orig_test = StandardDataset(df=test, label_name='income-per-year',
            favorable_classes=['>50K', '>50K.'],
            protected_attribute_names=['race'],
            privileged_classes=[[1]],
            instance_weights_name=None,
            categorical_features=['workclass', 'education', 'marital-status', 'occupation',
                                                  'relationship', 'native-country'],
            features_to_keep=[],
            features_to_drop=['income', 'native-country', 'hours-per-week'], na_values=na_values,
            custom_preprocessing=custom_preprocessing, metadata=default_mappings)

privileged_groups = [{'race': 1}]
unprivileged_groups = [{'race': 0}]

X_train = data_orig_train.features
y_train = data_orig_train.labels.ravel()

X_test = data_orig_test.features
y_test = data_orig_test.labels.ravel()


# scaler = StandardScaler()
# X_train = scaler.fit_transform(X_train)
# X_test = scaler.transform(X_test)
# data_orig_test.features = X_test


class CustomLRG(AutoSklearnClassificationAlgorithm):
    def __init__(self,
                 penalty,
                 C,
                 dual,
                 random_state=None
                 ):
        self.penalty = penalty
        self.C = C
        self.dual = dual
        self.random_state = random_state

    def fit(self, X, y):
        from sklearn.linear_model import LogisticRegression
        self.estimator = LogisticRegression(
            penalty=self.penalty,
            C=self.C,
            dual=self.dual,
            random_state=self.random_state
        )
        self.estimator.fit(X, y)
        return self

    def predict(self, X):
        if self.estimator is None:
            raise NotImplementedError()
        return self.estimator.predict(X)

    def predict_proba(self, X):
        if self.estimator is None:
            raise NotImplementedError()
        return self.estimator.predict_proba(X)

    @staticmethod
    def get_properties(dataset_properties=None):
        return {'shortname': 'LRG',
                'name': 'LRG Classifier',
                'handles_regression': False,
                'handles_classification': True,
                'handles_multiclass': True,
                'handles_multilabel': False,
                'handles_multioutput': False,
                'is_deterministic': False,
                # Both input and output must be tuple(iterable)
                'input': [DENSE, SIGNED_DATA, UNSIGNED_DATA],
                'output': [PREDICTIONS]}

    @staticmethod
    def get_hyperparameter_search_space(dataset_properties=None):
        cs = ConfigurationSpace()

        # The maximum number of features used in the forest is calculated as m^max_features, where
        # m is the total number of features, and max_features is the hyperparameter specified below.
        # The default is 0.5, which yields sqrt(m) features as max_features in the estimator. This
        # corresponds with Geurts' heuristic.

        penalty = CategoricalHyperparameter(name='penalty', choices=["l2"], default_value='l2')
        C = CategoricalHyperparameter(name='C', choices=[1e-4, 1e-3, 1e-2, 1e-1, 0.5, 1., 5., 10., 15.],
                                      default_value=1.)
        dual = CategoricalHyperparameter(name='dual', choices=[False], default_value=False)

        cs.add_hyperparameters([penalty, C, dual])
        return cs


autosklearn.pipeline.components.classification.add_classifier(CustomLRG)
cs = CustomLRG.get_hyperparameter_search_space()
print(cs)


############################################################################
# Custom metrics definition
# =========================

def accuracy(solution, prediction):
    metric_id = 1
    protected_attr = 'race'
    with open('test_split.txt') as f:
        first_line = f.read().splitlines()
        last_line = first_line[-1]
        split = list(last_line.split(","))
    for i in range(len(split)):
        split[i] = int(split[i])

    subset_data_orig_train = data_orig_train.subset(split)

    if os.stat("beta.txt").st_size == 0:

        default = LogisticRegression()
        degrees = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]
        mutation_strategies = {"0": [1, 0], "1": [0, 1]}
        dataset_orig = subset_data_orig_train
        res = create_baseline(default, dataset_orig, privileged_groups, unprivileged_groups,
                              data_splits=10, repetitions=10, odds=mutation_strategies, options=[0, 1],
                              degrees=degrees)
        acc0 = np.array([np.mean([row[0] for row in res["0"][degree]]) for degree in degrees])
        acc1 = np.array([np.mean([row[0] for row in res["1"][degree]]) for degree in degrees])
        fair0 = np.array([np.mean([row[metric_id] for row in res["0"][degree]]) for degree in degrees])
        fair1 = np.array([np.mean([row[metric_id] for row in res["1"][degree]]) for degree in degrees])

        if min(acc0) > min(acc1):
            beta = (max(acc0) - min(acc0)) / (max(acc0) - min(acc0) + max(fair0))
        else:
            beta = (max(acc1) - min(acc1)) / (max(acc1) - min(acc1) + max(fair1))

        f = open("beta.txt", "w")
        f.write(str(beta))
        f.close()
    else:
        f = open("beta.txt", "r")
        beta = float(f.read())
        f.close()
        # print('yyyy')
    # print(beta)
    beta += 0.2
    if beta > 1.0:
        beta = 1.0

    try:
        num_keys = sum(1 for line in open('num_keys.txt'))
        print(num_keys)
        beta -= 0.050 * int(int(num_keys) / 10)
        if beta < 0.0:
            beta = 0
        if int(num_keys) % 10 == 0:
            os.remove(temp_path + "/.auto-sklearn/ensemble_read_losses.pkl")
        f.close()
    except FileNotFoundError:
        pass
    fairness_metrics = [1 - np.mean(solution == prediction),
                        disparate_impact(subset_data_orig_train, prediction, protected_attr),
                        statistical_parity_difference(subset_data_orig_train, prediction, protected_attr),
                        equal_opportunity_difference(subset_data_orig_train, prediction, solution, protected_attr),
                        average_odds_difference(subset_data_orig_train, prediction, solution, protected_attr)]

    print(fairness_metrics[metric_id], 1 - np.mean(solution == prediction),
          fairness_metrics[metric_id] * beta + (1 - np.mean(solution == prediction)) * (1 - beta), beta)

    return fairness_metrics[metric_id] * beta + (1 - np.mean(solution == prediction)) * (1 - beta)


############################################################################
# Second example: Use own accuracy metric
# =======================================
print("#" * 80)
print("Use self defined accuracy metric")
accuracy_scorer = autosklearn.metrics.make_scorer(
    name="fair+acc",
    score_func=accuracy,
    optimum=1,
    greater_is_better=False,
    needs_proba=False,
    needs_threshold=False,
)

############################################################################
# Build and fit a classifier
# ==========================
automl = autosklearn.classification.AutoSklearnClassifier(
    time_left_for_this_task=60 * 60,
    # per_run_time_limit=500,
    memory_limit=10000000,
    include_estimators=['CustomLRG'],
    ensemble_size=1,
    include_preprocessors=['fast_ica', 'extra_trees_preproc_for_classification', 'pca'],
    tmp_folder=temp_path,
    delete_tmp_folder_after_terminate=False,
    metric=accuracy_scorer
)
automl.fit(X_train, y_train)

###########################################################################
# Get the Score of the final ensemble
# ===================================

print(automl.show_models())
cs = automl.get_configuration_space(X_train, y_train)

a_file = open("adult_lrg_di_60sp" + str(now) + ".pkl", "wb")
pickle.dump(automl.cv_results_, a_file)
a_file.close()

a_file1 = open("automl_adult_lrg_di_60sp" + str(now) + ".pkl", "wb")
pickle.dump(automl, a_file1)
a_file1.close()

predictions = automl.predict(X_test)
print(predictions)
print(y_test, len(predictions))
print("DI-Accuracy score:", sklearn.metrics.accuracy_score(y_test, predictions))
print(disparate_impact(data_orig_test, predictions, 'race'))
print(statistical_parity_difference(data_orig_test, predictions, 'race'))
print(equal_opportunity_difference(data_orig_test, predictions, y_test, 'race'))
print(average_odds_difference(data_orig_test, predictions, y_test, 'race'))
