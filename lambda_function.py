import json
import boto3
import uuid
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("Tasks")  # <<-- mesmo nome da sua tabela


# Converte Decimal -> float pra não dar erro no json.dumps
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def create_task(body):
    task_id = str(uuid.uuid4())

    title = body.get("title")
    description = body.get("description")
    date = body.get("date")  # formato 'YYYY-MM-DD'

    if not title or not date:
        return response(400, {"message": "Campos 'title' e 'date' são obrigatórios."})

    item = {
        "id": task_id,
        "title": title,
        "description": description or "",
        "date": date,
    }

    table.put_item(Item=item)
    return response(201, item)


def get_task(task_id):
    result = table.get_item(Key={"id": task_id})
    item = result.get("Item")

    if not item:
        return response(404, {"message": "Tarefa não encontrada."})

    return response(200, item)


def update_task(task_id, body):
    update_expression_parts = []
    expression_attribute_values = {}

    if "title" in body:
        update_expression_parts.append("title = :t")
        expression_attribute_values[":t"] = body["title"]

    if "description" in body:
        update_expression_parts.append("description = :d")
        expression_attribute_values[":d"] = body["description"]

    if "date" in body:
        update_expression_parts.append("date = :dt")
        expression_attribute_values[":dt"] = body["date"]

    if not update_expression_parts:
        return response(400, {"message": "Nenhum campo para atualizar."})

    update_expression = "SET " + ", ".join(update_expression_parts)

    try:
        result = table.update_item(
            Key={"id": task_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW",
        )
    except Exception as e:
        return response(500, {"message": f"Erro ao atualizar: {str(e)}"})

    return response(200, result.get("Attributes"))


def delete_task(task_id):
    result = table.get_item(Key={"id": task_id})
    if "Item" not in result:
        return response(404, {"message": "Tarefa não encontrada."})

    table.delete_item(Key={"id": task_id})
    return response(204, {})  # sem corpo


def get_tasks_by_date(query_params):
    date = None
    if query_params:
        date = query_params.get("date")

    if not date:
        return response(400, {"message": "Parâmetro 'date' é obrigatório. Ex: /tasks?date=2025-12-04"})

    from boto3.dynamodb.conditions import Attr

    result = table.scan(
        FilterExpression=Attr("date").eq(date)
    )
    items = result.get("Items", [])
    return response(200, items)


def lambda_handler(event, context):
    print("Evento recebido:", json.dumps(event))

    route_key = event.get("routeKey")  # "GET /tasks", "POST /tasks", etc.
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except Exception:
            body = {}

    try:
        # POST /tasks
        if route_key == "POST /tasks":
            return create_task(body)

        # GET /tasks/{id}
        if route_key == "GET /tasks/{id}":
            task_id = path_params.get("id")
            if not task_id:
                return response(400, {"message": "Parâmetro 'id' é obrigatório."})
            return get_task(task_id)

        # PUT /tasks/{id}
        if route_key == "PUT /tasks/{id}":
            task_id = path_params.get("id")
            if not task_id:
                return response(400, {"message": "Parâmetro 'id' é obrigatório."})
            return update_task(task_id, body)

        # DELETE /tasks/{id}
        if route_key == "DELETE /tasks/{id}":
            task_id = path_params.get("id")
            if not task_id:
                return response(400, {"message": "Parâmetro 'id' é obrigatório."})
            return delete_task(task_id)

        # GET /tasks (com ou sem ?date=)
        if route_key == "GET /tasks":
            if "date" in query_params:
                return get_tasks_by_date(query_params)
            else:
                result = table.scan()
                items = result.get("Items", [])
                return response(200, items)

        return response(404, {"message": "Rota não encontrada."})

    except Exception as e:
        print("Erro na Lambda:", str(e))
        return response(500, {"message": f"Erro interno: {str(e)}"})
