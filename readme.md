## Inspiration
Our inspiration came from the growing demand for intelligent applications that provide accurate and context-aware responses to user queries. We wanted to learn to create a system that combines the power of AI with the vast knowledge available online, enabling users to access information quickly and effectively.

## What it does
The project is an AWS Bedrock LLM-powered chat application designed to answer questions based on a curated knowledge base. Leveraging AWS Bedrock, it provides users with insightful and relevant information, with an interactive Q&A interface.

## How we built it
We built the project using AWS services, starting with data ingestion from an S3 bucket. We employed Amazon Titan embeddings to convert this data into searchable formats and indexed it using OpenSearch Serverless. The Amazon Bedrock Knowledge Base API integration allowed us to efficiently retrieve relevant information based on user queries, which were then processed through a large language model to generate coherent responses. A user-friendly interface was developed using Streamlit for seamless interaction.

## Challenges we ran into
One of the main challenges was ensuring fast and *accurate* retrieval of information from a large dataset, which required optimizing our embedding and search processes. Additionally, managing the complexity of user queries and maintaining the relevance of responses without retraining the underlying models posed significant hurdles. Balancing the performance of the application with its accuracy was crucial for a successful user experience.

## Accomplishments that we're proud of
We are proud of successfully building an end-to-end AI-driven application that integrates multiple AWS services seamlessly. The ability to deliver contextually relevant responses in real-time, while handling diverse queries, is a significant achievement. Our implementation of the Retrieval Augmented Generation (RAG) approach has also been a key highlight of the project. It has flaws but it was fun working on it as this was our 1st time using bedrock or AWS for an end to end project. We will try to fine-tune the model as our next step.

## What we learned
Throughout the project, we gained valuable insights into cloud-native AI development, particularly in utilizing AWS Bedrock and embedding models. We learned about the intricacies of data retrieval and the importance of fine-tuning search processes to enhance response quality. Our experience with building scalable applications in the cloud has significantly improved our technical skill set.

## What's next for Untitled
Moving forward, we plan to enhance the application by incorporating more diverse data sources to expand our knowledge base. We aim to refine the user experience by implementing additional features such as voice recognition and multi-language support. Continuous improvements in our model's accuracy and response time will also be a priority as we seek to make the application more robust and user-friendly.
