# Webhook Mailbox

This project configures Amazon Web Services, in particular [API Gateway][gateway], [Simple Queue Service][sqs], and [Lambda][lambda], to create an API endpoint which places incoming requests into a queue ("mailbox").

[gateway]: https://aws.amazon.com/api-gateway/
[lambda]: https://aws.amazon.com/lambda/
[sqs]: https://aws.amazon.com/sqs/

Requests can be popped off of this queue from behind a firewall and delivered to an internal service, without exposing that service to the Internet.


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

    $ python webhook-mailbox.py configure
    Configured queue webhook-mailbox-388cfb with the following credentials:
      AWS_ACCESS_KEY_ID=AKIATM5TRIWFWDM3I4GX
      AWS_SECRET_ACCESS_KEY=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

    URL: https://jofx96r5z4.execute-api.us-east-1.amazonaws.com/prod/


# Watch

The `watch` subcommand watches the queue. When a new message, it will issue a request to the given endpoint URL, copying the HTTP method, headers, URL parameters, and request body. The path is discarded.

    AWS_ACCESS_KEY_ID= \
    AWS_SECRET_ACCESS_KEY= \
    python webhook-mailbox.py watch \
      webhook-mailbox-e05a69 \
      https://server.local/endpoint


# Integration with Jenkins

The [Generic Webhook Trigger][gwt] plugin for Jenkins can be used to set up an HTTP endpoint to trigger a build.

[gwt]: https://plugins.jenkins.io/generic-webhook-trigger
[gwt-examples]: https://github.com/jenkinsci/generic-webhook-trigger-plugin/tree/master/src/test/resources/org/jenkinsci/plugins/gwt/bdd

Enable the trigger on your Jenkins project. It's a good idea to assign a token to it.

On the repository server, the hook URL should look like:

    https://xyzzy.execute-api.us-east-1.amazonaws.com/prod/?token=project-token

For additional configuration, such as to set which branch to build, see [these examples][gwt-examples].

Then, run the mailbox watcher with the corresponding queue name and the Jenkins trigger invocation URL:

    AWS_ACCESS_KEY_ID= \
    AWS_SECRET_ACCESS_KEY= \
    python webhook-mailbox.py watch \
      webhook-mailbox-e05a69 \
      https://jenkins.local/generic-webhook-trigger/invoke


# Future

It is possible the configuration could be done through [CloudFormation][] or [Terraform][] more robustly.

[CloudFormation]: https://aws.amazon.com/cloudformation/
[Terraform]: https://www.terraform.io/
