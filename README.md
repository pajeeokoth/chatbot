# chatbot

This repository contains an aiohttp-based Microsoft Bot Framework app in `mytravel/` with Conversational Language Understanding (CLU) integration.

## Structure
- `extraction_script.py`
- `P10_jupyternotebook.ipynb`
- `mytravel/` — aiohttp bot exposing `/api/messages` (CLU-enabled)

## MyTravel app
See `mytravel/README.md` for setup and CLU configuration.

The app runs on `http://localhost:3978` for local development.
# chatbot
chatbot to help users choose a travel offer
This project is to create a chatbot to help users choose a travel offer.
It is part of the OpenClassrooms "Build your own chatbot with Deep Learning" course.
The chatbot will be trained on a dataset of conversations between users and travel agents.
The dataset is in JSON format and contains information about the user's preferences, the travel offers, and the conversation history.
The chatbot will be implemented using Python and the TensorFlow library.
The project will be divided into the following steps:
1. Load and preprocess the dataset
2. Build and train the chatbot model
3. Evaluate the model
4. Deploy the chatbot
The dataset used in this project is the Frames dataset, which is available on GitHub:
