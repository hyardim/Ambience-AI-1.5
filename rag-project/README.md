# Ambience-AI-1.5

**A Specialized Clinical Decision Support System for Rheumatology & Neurology.**

## 📖 Project Overview

This project implements a **Microservices-based Retrieval-Augmented Generation (RAG)** system designed to assist clinicians with accurate, guideline-backed answers. Unlike generic chatbots, this system functions as a "hyper-tuned" medical specialist. It decouples application logic from high-performance inference to ensure scalability and clinical safety.

The core logic is orchestrated by **LangChain**, which retrieves context from a curated **Vector Database (Digital Library)** of UK clinical guidelines. This context is processed by **MED-42**, a specialized Large Language Model (LLM) fine-tuned for medical reasoning. The inference engine runs exclusively on the **Intel Gaudi 2 (Habana HPU)** accelerator using the SynapseAI stack, providing high-throughput, low-latency token generation.

## 🏗️ Technical Architecture

The system follows a decoupled microservices topology:

* **Orchestrator (LangChain):** Acts as the central controller (CPU-bound). It handles prompt engineering, tool selection, and conversation memory.
* **Digital Library (Vector DB):** Stores high-dimensional embeddings of Rheumatology and Neurology clinical guidelines for semantic retrieval.
* **Neural Engine (Intel Gaudi 2):** A dedicated inference service running **Hugging Face TGI** on the Habana SynapseAI stack. This service executes the **MED-42** model.
* **Safety Layer:** Implements automated "Red Teaming" and strict output validation to minimize hallucination and ensure clinical disclaimer compliance.

## ⚡ Hardware & Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Hardware** | **Intel Gaudi 2 (HPU)** | Dedicated ASIC for accelerated tensor operations. |
| **Driver Stack** | **SynapseAI** | Habana's software stack replacing standard CUDA libraries. |
| **Model** | **MED-42** | "Hyper-tuned" Llama-based model for clinical reasoning. |
| **Framework** | **LangChain** | Application orchestration and RAG logic. |

## 🎯 Key Features

* **Domain Specific:** Hyper-tuned specifically for **Rheumatology** and **Neurology** queries.
* **Grounded Generation:** Every response is grounded in retrieved text chunks from verified PDF guidelines (RAG).
* **HPU Accelerated:** Optimized for the unique memory architecture of the Habana Gaudi 2.
* **Clinical Safety:** Includes adversarial defense mechanisms and mandatory disclaimer injection.
