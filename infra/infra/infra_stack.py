import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_dynamodb as ddb,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_event_sources as eventsources,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_apigatewayv2_authorizers as apigwv2_auth,
    aws_cognito as cognito,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 — importa bucket existente ────────────────────────────────────
        media_bucket = s3.Bucket.from_bucket_name(
            self, "SiabMediaBucket", "siab-media-dev"
        )

        # ── DynamoDB — configuração base ──────────────────────────────────────
        _common = dict(
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        projects = ddb.Table(
            self, "SiabProjects",
            table_name="siab-projects",
            partition_key=ddb.Attribute(name="tenant_id",           type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="client_id#project_id", type=ddb.AttributeType.STRING),
            **_common,
        )

        videos_table = ddb.Table(
            self, "SiabVideos",
            table_name="siab-videos",
            partition_key=ddb.Attribute(name="tenant_id",          type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="project_id#video_id", type=ddb.AttributeType.STRING),
            **_common,
        )

        cameras = ddb.Table(
            self, "SiabCameras",
            table_name="siab-cameras",
            partition_key=ddb.Attribute(name="tenant_id",           type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="project_id#camera_id", type=ddb.AttributeType.STRING),
            **_common,
        )

        appearances = ddb.Table(
            self, "SiabAppearances",
            table_name="siab-appearances",
            partition_key=ddb.Attribute(name="tenant_id",             type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="video_id#appearance_id", type=ddb.AttributeType.STRING),
            **_common,
        )
        appearances.add_global_secondary_index(
            index_name="by-species",
            partition_key=ddb.Attribute(name="tenant_id#project_id", type=ddb.AttributeType.STRING),
            sort_key=     ddb.Attribute(name="species#appearance_id", type=ddb.AttributeType.STRING),
            projection_type=ddb.ProjectionType.ALL,
        )
        appearances.add_global_secondary_index(
            index_name="by-review-status",
            partition_key=ddb.Attribute(name="tenant_id#review_status",  type=ddb.AttributeType.STRING),
            sort_key=     ddb.Attribute(name="project_id#appearance_id", type=ddb.AttributeType.STRING),
            projection_type=ddb.ProjectionType.ALL,
        )

        reviews = ddb.Table(
            self, "SiabReviews",
            table_name="siab-reviews",
            partition_key=ddb.Attribute(name="tenant_id",                type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="appearance_id#reviewed_at", type=ddb.AttributeType.STRING),
            **_common,
        )

        frame_annotations = ddb.Table(
            self, "SiabFrameAnnotations",
            table_name="siab-frame-annotations",
            partition_key=ddb.Attribute(name="tenant_id",             type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="appearance_id#frame_idx", type=ddb.AttributeType.STRING),
            **_common,
        )

        species = ddb.Table(
            self, "SiabSpecies",
            table_name="siab-species",
            partition_key=ddb.Attribute(name="species_id", type=ddb.AttributeType.STRING),
            **_common,
        )

        invites = ddb.Table(
            self, "SiabInvites",
            table_name="siab-invites",
            partition_key=ddb.Attribute(name="tenant_id", type=ddb.AttributeType.STRING),
            sort_key=     ddb.Attribute(name="email",     type=ddb.AttributeType.STRING),
            **_common,
        )
        invites.add_global_secondary_index(
            index_name="email-index",
            partition_key=ddb.Attribute(name="email", type=ddb.AttributeType.STRING),
            projection_type=ddb.ProjectionType.ALL,
        )

        # ── SQS — filas do pipeline com DLQs ─────────────────────────────────
        # Visibility timeout >= 6x o timeout da Lambda que consome a fila.
        # Lambda timeout = 15 min → visibility = 90 min.
        _dlq_retention = Duration.days(14)
        _lambda_timeout = Duration.minutes(15)
        _queue_visibility = Duration.minutes(90)

        videos_dlq = sqs.Queue(
            self, "VideosDLQ",
            queue_name="siab-videos-dlq",
            retention_period=_dlq_retention,
        )
        videos_queue = sqs.Queue(
            self, "VideosQueue",
            queue_name="siab-videos",
            visibility_timeout=_queue_visibility,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=videos_dlq,
            ),
        )

        frames_dlq = sqs.Queue(
            self, "FramesDLQ",
            queue_name="siab-frames-dlq",
            retention_period=_dlq_retention,
        )
        frames_queue = sqs.Queue(
            self, "FramesQueue",
            queue_name="siab-frames",
            visibility_timeout=_queue_visibility,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=frames_dlq,
            ),
        )

        detections_dlq = sqs.Queue(
            self, "DetectionsDLQ",
            queue_name="siab-detections-dlq",
            retention_period=_dlq_retention,
        )
        detections_queue = sqs.Queue(
            self, "DetectionsQueue",
            queue_name="siab-detections",
            visibility_timeout=_queue_visibility,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=detections_dlq,
            ),
        )

        # ── Lambda — Ingester (imagem leve, sem PyTorch) ──────────────────────
        # Build context: ".." = raiz do projeto (infra/../)
        ingester_fn = _lambda.DockerImageFunction(
            self, "IngesterFn",
            function_name="siab-ingester",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="../pipeline",
                file="Dockerfile.ingester",
            ),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=512,
            timeout=_lambda_timeout,
            environment={
                "SIAB_BUCKET":      "siab-media-dev",
                "FRAMES_QUEUE_URL": frames_queue.queue_url,
            },
        )

        # ── Lambda — MegaDetector (imagem ML, STAGE=megadetector) ────────────
        megadetector_fn = _lambda.DockerImageFunction(
            self, "MegaDetectorFn",
            function_name="siab-megadetector",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="../pipeline",
                file="Dockerfile",
            ),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=3008,
            timeout=_lambda_timeout,
            environment={
                "SIAB_BUCKET":          "siab-media-dev",
                "STAGE":                "megadetector",
                "DETECTIONS_QUEUE_URL": detections_queue.queue_url,
                "MD_CACHE_DIR":         "/tmp/models",
                "MD_THRESHOLD":         "0.1",
            },
        )

        # ── Lambda — SpeciesNet (mesma imagem ML, STAGE=speciesnet) ──────────
        speciesnet_fn = _lambda.DockerImageFunction(
            self, "SpeciesNetFn",
            function_name="siab-speciesnet",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="../pipeline",
                file="Dockerfile",
            ),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=3008,
            timeout=_lambda_timeout,
            environment={
                "SIAB_BUCKET":         "siab-media-dev",
                "STAGE":               "speciesnet",
                "APPEARANCES_TABLE":   appearances.table_name,
                "SIAB_COUNTRY":        "BRA",
                "GAP_FRAMES":          "15",
                "SN_MODEL":            "/tmp/models/speciesnet/v4.0.3a",
                "SN_MODEL_S3_PREFIX":  "models/speciesnet/v4.0.3a",
                "SN_MODEL_LOCAL_DIR":  "/tmp/models/speciesnet/v4.0.3a",
                "SN_MODEL_VERSION":    "speciesnet-v5.0.5",
            },
        )

        # ── IAM — Ingester ───────────────────────────────────────────────────
        # Lê vídeos do S3 + escreve frames no S3 + envia para frames_queue
        media_bucket.grant_read(ingester_fn)
        media_bucket.grant_put(ingester_fn)
        frames_queue.grant_send_messages(ingester_fn)

        # ── IAM — MegaDetector ───────────────────────────────────────────────
        # Lê frames do S3 + lê modelo do S3 + envia para detections_queue
        media_bucket.grant_read(megadetector_fn)
        detections_queue.grant_send_messages(megadetector_fn)

        # ── IAM — SpeciesNet ─────────────────────────────────────────────────
        # Lê frames do S3 + escreve Aparições no DynamoDB
        media_bucket.grant_read(speciesnet_fn)
        appearances.grant_write_data(speciesnet_fn)

        # ── Event Source Mappings (SQS → Lambda) ─────────────────────────────
        ingester_fn.add_event_source(
            eventsources.SqsEventSource(
                videos_queue,
                batch_size=1,
                report_batch_item_failures=True,
            )
        )
        megadetector_fn.add_event_source(
            eventsources.SqsEventSource(
                frames_queue,
                batch_size=1,
                report_batch_item_failures=True,
            )
        )
        speciesnet_fn.add_event_source(
            eventsources.SqsEventSource(
                detections_queue,
                batch_size=1,
                report_batch_item_failures=True,
            )
        )

        # ── Lambda — API FastAPI (Mangum) ─────────────────────────────────────
        api_fn = _lambda.DockerImageFunction(
            self, "ApiFn",
            function_name="siab-api",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="../",
                file="backend/Dockerfile",
            ),
            architecture=_lambda.Architecture.ARM_64,
            memory_size=512,
            timeout=Duration.seconds(30),
            environment={
                "SIAB_BUCKET":              "siab-media-dev",
                "APPEARANCES_TABLE":        appearances.table_name,
                "REVIEWS_TABLE":            reviews.table_name,
                "FRAME_ANNOTATIONS_TABLE":  frame_annotations.table_name,
                "VIDEOS_QUEUE_NAME":        videos_queue.queue_name,
                "INVITES_TABLE":            invites.table_name,
            },
        )

        # IAM — API Lambda precisa ler/escrever S3 + todas as tabelas DDB + SQS
        media_bucket.grant_read_write(api_fn)
        for table in [appearances, reviews, frame_annotations, projects, videos_table, cameras, species, invites]:
            table.grant_read_write_data(api_fn)
        videos_queue.grant_send_messages(api_fn)

        # ── Lambda — Pre Sign-up Trigger (Python puro, sem ML) ───────────────
        pre_signup_fn = _lambda.Function(
            self, "PreSignupFn",
            function_name="siab-pre-signup",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/pre_signup"),
            timeout=Duration.seconds(10),
            environment={
                "INVITES_TABLE": invites.table_name,
                # COGNITO_USER_POOL_ID não é passado aqui — lido de event["userPoolId"]
                # para evitar dependência circular com o User Pool (ver add_trigger abaixo).
            },
        )
        invites.grant_read_write_data(pre_signup_fn)

        # ── Cognito — User Pool com email + Google OAuth ──────────────────────
        user_pool = cognito.UserPool(
            self, "SiabUserPool",
            user_pool_name="siab-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=False,
                require_symbols=False,
            ),
            custom_attributes={
                "tenant_id": cognito.StringAttribute(mutable=True),
                "role":      cognito.StringAttribute(mutable=True, max_len=50),
            },
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Google IdP — credenciais devem existir em siab/google-oauth antes do deploy
        google_provider = cognito.UserPoolIdentityProviderGoogle(
            self, "GoogleProvider",
            user_pool=user_pool,
            client_id=cdk.SecretValue.secrets_manager(
                "siab/google-oauth", json_field="clientId"
            ).unsafe_unwrap(),
            client_secret_value=cdk.SecretValue.secrets_manager(
                "siab/google-oauth", json_field="clientSecret"
            ),
            attribute_mapping=cognito.AttributeMapping(
                email=cognito.ProviderAttribute.GOOGLE_EMAIL,
                fullname=cognito.ProviderAttribute.GOOGLE_NAME,
            ),
            scopes=["email", "profile", "openid"],
        )

        web_client = user_pool.add_client(
            "SiabWebClient",
            user_pool_client_name="siab-web-client",
            generate_secret=True,
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[
                    "https://frontend-siab.vercel.app/api/auth/callback/cognito",
                    "https://frontend-beta-seven-49.vercel.app/api/auth/callback/cognito",
                    "http://localhost:3001/api/auth/callback/cognito",
                ],
                logout_urls=[
                    "https://frontend-siab.vercel.app/login",
                    "https://frontend-beta-seven-49.vercel.app/login",
                    "http://localhost:3001/login",
                ],
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO,
                cognito.UserPoolClientIdentityProvider.GOOGLE,
            ],
        )
        web_client.node.add_dependency(google_provider)

        user_pool.add_domain(
            "SiabDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix="siab-auth"),
        )

        # ── Pre Sign-up Trigger — wiring + IAM ───────────────────────────────
        # add_trigger adiciona automaticamente a Lambda permission para o Cognito invocar.
        # NÃO passamos user_pool.user_pool_id como env var — isso criaria dependência
        # circular (UserPool → Lambda trigger → Lambda env → UserPool).
        # O handler lê o ID diretamente de event["userPoolId"] (presente em todos os triggers).
        user_pool.add_trigger(cognito.UserPoolOperation.PRE_SIGN_UP, pre_signup_fn)
        pre_signup_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:AdminUpdateUserAttributes"],
                # ID literal (não token CDK) para evitar dependência circular e
                # restringir ao pool exato. Se o pool for recriado, atualizar aqui
                # e em backend/api.py:49 (_USER_POOL_ID).
                resources=[
                    f"arn:aws:cognito-idp:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:userpool/us-east-1_muBMGRYkB"
                ],
            )
        )

        # ── Post Confirmation Trigger — wiring + IAM ─────────────────────────
        # O Pre Sign-up dispara ANTES do utilizador existir para fluxos federados
        # (Google) → admin_update_user_attributes falha com UserNotFoundException.
        # O Post Confirmation dispara DEPOIS do utilizador estar criado e confirmado
        # → aqui a chamada funciona correctamente.
        post_confirmation_fn = _lambda.Function(
            self, "PostConfirmationFn",
            function_name="siab-post-confirmation",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/post_confirmation"),
            timeout=Duration.seconds(10),
            environment={
                "INVITES_TABLE": invites.table_name,
            },
        )
        invites.grant_read_data(post_confirmation_fn)
        user_pool.add_trigger(cognito.UserPoolOperation.POST_CONFIRMATION, post_confirmation_fn)
        post_confirmation_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:AdminUpdateUserAttributes"],
                # Mesmo padrão do pre_signup_fn: ID literal para evitar wildcard e ciclo CDK.
                resources=[
                    f"arn:aws:cognito-idp:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:userpool/us-east-1_muBMGRYkB"
                ],
            )
        )

        # Injeta UserPool ID na Lambda da API
        api_fn.add_environment("COGNITO_USER_POOL_ID", user_pool.user_pool_id)
        api_fn.add_environment("COGNITO_REGION", "us-east-1")

        jwt_auth = apigwv2_auth.HttpJwtAuthorizer(
            "CognitoAuth",
            jwt_issuer=f"https://cognito-idp.us-east-1.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[web_client.user_pool_client_id],
        )

        # ── HTTP API Gateway v2 ────────────────────────────────────────────────
        http_api = apigwv2.HttpApi(
            self, "SiabHttpApi",
            api_name="siab-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=[
                    "https://frontend-siab.vercel.app",
                    "https://frontend-beta-seven-49.vercel.app",
                    "http://localhost:3000",
                    "http://localhost:3001",
                ],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["*"],
            ),
        )
        http_api.add_routes(
            path="/{proxy+}",
            methods=[
                apigwv2.HttpMethod.GET,
                apigwv2.HttpMethod.POST,
                apigwv2.HttpMethod.PUT,
                apigwv2.HttpMethod.PATCH,
                apigwv2.HttpMethod.DELETE,
            ],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                "ApiIntegration", api_fn,
            ),
            authorizer=jwt_auth,
        )

        # ── Lambda — Consolidator (Python puro, sem ML) ───────────────────────
        # Descobre projetos activos via scan de siab-appearances e chama
        # consolidate_project_appearances() para cada (tenant_id, project_id).
        # A siab-projects está vazia no piloto — ver comentário em handler.py.
        consolidator_fn = _lambda.Function(
            self, "ConsolidatorFn",
            function_name="siab-consolidator",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("lambda/consolidator"),
            timeout=Duration.minutes(15),
            memory_size=256,
            environment={
                "APPEARANCES_TABLE": appearances.table_name,
                "GAP_SECONDS":       "300",
            },
        )
        appearances.grant_read_write_data(consolidator_fn)

        # EventBridge Schedule: dispara a cada 15 minutos
        consolidator_rule = events.Rule(
            self, "ConsolidatorSchedule",
            rule_name="siab-consolidator-schedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),
        )
        consolidator_rule.add_target(
            events_targets.LambdaFunction(consolidator_fn)
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "ApiUrl",          value=http_api.api_endpoint)
        CfnOutput(self, "UserPoolId",      value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId",value=web_client.user_pool_client_id)
        CfnOutput(self, "CognitoDomain",   value="https://siab-auth.auth.us-east-1.amazoncognito.com")
        CfnOutput(self, "BucketName",              value=media_bucket.bucket_name)
        CfnOutput(self, "ProjectsTable",           value=projects.table_name)
        CfnOutput(self, "VideosTable",             value=videos_table.table_name)
        CfnOutput(self, "CamerasTable",            value=cameras.table_name)
        CfnOutput(self, "AppearancesTable",        value=appearances.table_name)
        CfnOutput(self, "ReviewsTable",            value=reviews.table_name)
        CfnOutput(self, "FrameAnnotationsTable",   value=frame_annotations.table_name)
        CfnOutput(self, "SpeciesTable",            value=species.table_name)
        CfnOutput(self, "InvitesTable",            value=invites.table_name)
        CfnOutput(self, "VideosQueueUrl",      value=videos_queue.queue_url)
        CfnOutput(self, "FramesQueueUrl",      value=frames_queue.queue_url)
        CfnOutput(self, "DetectionsQueueUrl",  value=detections_queue.queue_url)
        CfnOutput(self, "IngesterFnArn",            value=ingester_fn.function_arn)
        CfnOutput(self, "MegaDetectorFnArn",        value=megadetector_fn.function_arn)
        CfnOutput(self, "SpeciesNetFnArn",          value=speciesnet_fn.function_arn)
        CfnOutput(self, "PostConfirmationFnArn",    value=post_confirmation_fn.function_arn)
        CfnOutput(self, "ConsolidatorFnArn",        value=consolidator_fn.function_arn)
