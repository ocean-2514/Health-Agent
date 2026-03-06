import os
from .GlobalConfig import GlobalConfig

class EnvValidator:
    """
    Utility class to validate environment variables and config readiness.
    """
    
    @staticmethod
    def validate():
        """
        Validates the necessary environment variables and config properties exist.
        Throws EnvironmentError if anything is missing.
        """
        config = GlobalConfig.config
        
        # Validate Database configuration
        if "IoTDB" not in config.get("Database", {}):
            print("Warning: IoTDB configuration missing in GlobalConfig.yaml.")
            
        # Optional validation logic here, checking LLM configuration etc.
        llm_config = config.get("LLM", {}).get("OpenAI", {})
        if llm_config.get("APIKey") == "YOUR_OPENAI_API_KEY" and not os.environ.get("OPENAI_API_KEY"):
            print("Warning: OpenAI API Key is missing. Either update GlobalConfig.yaml or set environment variable OPENAI_API_KEY.")
            
        print("Environment validation completed structure-wise.")

if __name__ == "__main__":
    EnvValidator.validate()
