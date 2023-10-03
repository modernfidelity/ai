# AI/ML/RL

Notes on the field of artifical intelligence & machine learning on the AWS cloud.

A computer program is said to learn from experience E with respect to some class of tasks T and performance measure P, if its performance at tasks in T, as measured by P, improves with experience

## Applications

- Recommendation Engines
- Demand Forecasting
- Computer Vision
- Fraud Detection
- Medical Diagnosis
- Stock Market Forecasting
- Sentiment Analysis 

## Concepts 

Terminology 

- **Features**
    - Each item or piece of data is described by a number of features 
- **Labels**
    - Each item or piece of data may be tagged with a known classification result
- **Instances**
    - An instance or sample is an item within the dataset, each instance will have a set features, and may also have a label assigned to it. 


**Learning Phases**

1. Dataset Collection
2. Featurisation
3. Model Training
4. Model Testing
5. Best Model

## Machine Learning Types

### Supervised Learning
Create a predictive machine learning models using both features and labels. 

- Processes past observations 
- Train Models
- Mapping Function
    - Features > Labels 
- Predict future outcomes (Labels)

**Problem Types**

1. If the output Label is categorical then use a classification model
2. If the output Label is numeric then use a regression model

- **Classification**
    - If the output data mapping is discreet i.e. is cat ? 
    - Types of Algorithms 
        - Linear Regression
        - Logisitc Regression
        - Support Vector Machines
        - Naive Bayes
        - K Nearest Neighbour
        - Decision Trees
        - Random Forest
- **Regression**
    - If the output data mapping is continuous i.e. +7.5 Celsius 
    - Types of Algorithms 
        - Linear Regression
        - Decision Trees
        - Random Forest

The above can be used to solve many business problems
- How much is this home worth ? 
- How many customers will watch season 2 ?
- Is this cancer malignant ? 
- Will this customer default on a loan ? 


**Datasets**

Data split into a basic 80% 20% share, where 80% is used for training and 20% for testing. (More phases recommended)

### Unsupervised Learning
Group and discover patterns based only on features

- Clustering

