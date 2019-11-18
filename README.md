# Webhook Proxy

This project configures Amazon Web Services, in particular [API Gateway][gateway], [Simple Queue Service][sqs], and [Lambda][lambda], to create an API endpoint which places incoming requests into a queue.

[gateway]: https://aws.amazon.com/api-gateway/
[lambda]: https://aws.amazon.com/lambda/
[sqs]: https://aws.amazon.com/sqs/

Requests can popped off of this queue from behind a firewall and forwarded to an internal service, without exposing that service to the Internet.


# Install

First, configure a virtual environment and install dependencies:

    virtualenv --python=python3 .venv
    .venv/bin/activate
    pip install -r requirements.txt
    command -v rehash && rehash

[Configure the AWS command line][aws-config] with your credentials and default region. [Other configuration methods][boto3-config], such as environment variables, are available.

[aws-config]: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html#cli-quick-configuration
[boto3-config]: https://boto3.amazonaws.com/v1/documentation/api/1.9.42/guide/configuration.html

**Security considerations:** Do not leave your AWS credentials lying around in `~/.aws` or your shell history file on the server. The `configure` stage generates credentials with limited privileges that can be safely deployed instead.


# Configure

The `configure` subcommand will automatically provision the necessary AWS resources and return credentials and an HTTP endpoint URL: 

    $ python webhook-proxy.py configure
    Configured queue webhook-proxy-388cfb with the following credentials:
      AWS_ACCESS_KEY_ID=AKIATM5TRIWFWDM3I4GX
      AWS_SECRET_ACCESS_KEY=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

    URL: https://jofx96r5z4.execute-api.us-east-1.amazonaws.com/prod/


# Future

It is possible the configuration could be done through [Terraform][] more robustly.

[Terraform]: https://www.terraform.io/
