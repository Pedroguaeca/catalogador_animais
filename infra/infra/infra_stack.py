import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_dynamodb as ddb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_event_sources as eventsources,
    aws_s3 as s3,
    aws_sqs as sqs,
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
            partition_key=ddb.Attribute(name="tenant_id",              type=ddb.AttributeType.STRING),
            sort_key=    ddb.Attribute(name="video_id#frame_path",     type=ddb.AttributeType.STRING),
            **_common,
        )
        frame_annotations.add_global_secondary_index(
            index_name="by-video",
            partition_key=ddb.Attribute(name="tenant_id#video_id", type=ddb.AttributeType.STRING),
            sort_key=     ddb.Attribute(name="frame_idx",          type=ddb.AttributeType.NUMBER),
            projection_type=ddb.ProjectionType.ALL,
        )

        species = ddb.Table(
            self, "SiabSpecies",
            table_name="siab-species",
            partition_key=ddb.Attribute(name="species_id", type=ddb.AttributeType.STRING),
            **_common,
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

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "BucketName",          value=media_bucket.bucket_name)
        CfnOutput(self, "ProjectsTable",       value=projects.table_name)
        CfnOutput(self, "VideosTable",         value=videos_table.table_name)
        CfnOutput(self, "CamerasTable",        value=cameras.table_name)
        CfnOutput(self, "AppearancesTable",    value=appearances.table_name)
        CfnOutput(self, "ReviewsTable",        value=reviews.table_name)
        CfnOutput(self, "SpeciesTable",        value=species.table_name)
        CfnOutput(self, "VideosQueueUrl",      value=videos_queue.queue_url)
        CfnOutput(self, "FramesQueueUrl",      value=frames_queue.queue_url)
        CfnOutput(self, "DetectionsQueueUrl",  value=detections_queue.queue_url)
        CfnOutput(self, "IngesterFnArn",       value=ingester_fn.function_arn)
        CfnOutput(self, "MegaDetectorFnArn",   value=megadetector_fn.function_arn)
        CfnOutput(self, "SpeciesNetFnArn",     value=speciesnet_fn.function_arn)
