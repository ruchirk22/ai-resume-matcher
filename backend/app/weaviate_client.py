import weaviate
import weaviate.classes as wvc

# v4 connection method
client = weaviate.connect_to_local()

def setup_weaviate_schema():
    """
    Sets up the Weaviate schema using v4 syntax. Idempotent.
    """
    if not client.collections.exists("JobDescription"):
        client.collections.create(
            name="JobDescription",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(), # We provide our own vectors
            properties=[
                wvc.config.Property(name="user_id", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="content", data_type=wvc.config.DataType.TEXT),
            ]
        )
    
    if not client.collections.exists("Resume"):
        client.collections.create(
            name="Resume",
            vectorizer_config=wvc.config.Configure.Vectorizer.none(), # We provide our own vectors
            properties=[
                wvc.config.Property(name="user_id", data_type=wvc.config.DataType.INT),
                wvc.config.Property(name="candidate_name", data_type=wvc.config.DataType.TEXT),
                wvc.config.Property(name="content", data_type=wvc.config.DataType.TEXT),
            ]
        )

# Run setup when the application starts
setup_weaviate_schema()

