# MBTI Prediction System

A multilingual MBTI prediction web application that uses Natural Language Processing (NLP), voice input, scenario-based assessment, and career recommendations to provide users with personalized personality insights.

## Overview

The MBTI Prediction System is a web-based application designed to predict a user's Myers-Briggs Type Indicator (MBTI) personality type through multiple input methods. The system supports text-based personality input, voice transcription, and scenario-based questions, making the user experience more interactive and accessible.

This project also includes multilingual support, confidence scoring, a timeline tracker for previous results, and personalized career recommendations based on predicted MBTI types.

## Features

- Multilingual support:
  - English
  - Bahasa Melayu
  - Mandarin

- Multiple input methods:
  - Text input
  - Voice input with speech-to-text
  - Scenario-based personality test

- MBTI prediction using NLP and machine learning

- Top 3 predicted MBTI types with confidence scores

- Career recommendations based on MBTI type

- Timeline tracker to view previous personality results

- Resume-based initial profile input for cold start improvement

- User authentication and admin management

## Technologies Used

### Backend
- Python
- Flask
- SQLite

### Machine Learning / NLP
- Scikit-learn
- TF-IDF Vectorizer
- Logistic Regression

### Voice Processing
- Faster-Whisper
- OpenCC
- deep-translator

### Frontend
- HTML
- CSS
- JavaScript
- Jinja2 Templates

### Other Tools / Libraries
- Chart.js
- html2canvas
- OpenCV
- pytesseract
- pdf2image

## System Modules

### 1. User Account Module
- User registration
- Login and logout
- Email verification
- Password reset

### 2. MBTI Prediction Module
- Predicts MBTI personality type from text input
- Displays top 3 MBTI results
- Shows confidence scores

### 3. Voice Input Module
- Allows users to record or upload audio
- Converts speech to text
- Supports English, Malay, and Mandarin input

### 4. Scenario-Based Test Module
- Users answer personality-related scenario questions
- System calculates MBTI dimensions based on selected answers

### 5. Career Recommendation Module
- Suggests suitable careers based on predicted MBTI type

### 6. Timeline Tracker Module
- Stores and displays previous MBTI results
- Helps users observe personality trends over time

### 7. Initial Profile / Cold Start Module
- Collects user profile information
- Supports resume upload and OCR extraction
- Helps improve early-stage prediction when limited historical data is available

### 8. Admin Module
- Manage users
- Manage scenario questions and options
- Manage career recommendation content

## How It Works

The system predicts MBTI type using machine learning models trained on personality-related text. For text and voice input, the application processes the input and predicts personality preferences across the four MBTI dimensions:

- Introversion (I) / Extraversion (E)
- Intuition (N) / Sensing (S)
- Thinking (T) / Feeling (F)
- Judging (J) / Perceiving (P)

For scenario-based assessment, the system assigns scores to selected answers and determines the MBTI type based on accumulated dimension scores.

The final result includes:
- Top 3 MBTI personality types
- Confidence scores
- Personality descriptions
- Career recommendations
