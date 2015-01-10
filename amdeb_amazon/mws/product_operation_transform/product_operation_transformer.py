# -*- coding: utf-8 -*-

import logging

from ...shared.model_names import (
    MODEL_NAME_FIELD, RECORD_ID_FIELD, OPERATION_TYPE_FIELD,
    WRITE_FIELD_NAMES_FIELD,
)
from .operation_types import (
    CREATE_RECORD, UNLINK_RECORD,
)

from ...models_access import OdooProductAccess, ProductOperationAccess
from . import ProductUnlinkTransformer
from . import ProductCreateTransformer
from . import ProductWriteTransformer

_logger = logging.getLogger(__name__)


class ProductOperationTransformer(object):
    """
    Transform product operations into sync operations
    A product may be unlinked in Odoo -- be careful to check
    for create and write operation before transformation
    """
    def __init__(self, env, new_operations):
        self._new_operations = new_operations
        self._unlink_transformer = ProductUnlinkTransformer(
            env, new_operations)
        self._create_transformer = ProductCreateTransformer(env)
        self._writer_transformer = ProductWriteTransformer(env)
        self._odoo_product = OdooProductAccess(env)

        # this set keeps transformed model_name and record_id
        self._transformed_operations = set()

    def _check_create(self, operation):
        """
        Check if there is a create operation for the model name
        and record id.
        """
        creation = None
        creations = [
            element for element in self._new_operations if
            element[MODEL_NAME_FIELD] == operation[MODEL_NAME_FIELD] and
            element[RECORD_ID_FIELD] == operation[RECORD_ID_FIELD] and
            element[OPERATION_TYPE_FIELD] == CREATE_RECORD
        ]
        if creations:
            creation = creations[0]
        return creation

    def _merge_write(self, operation, write_values):
        # merge all writes that are ordered by operation id
        merged_values = write_values
        other_writes = [
            record for record in self._new_operations if
            record[MODEL_NAME_FIELD] == operation[MODEL_NAME_FIELD] and
            record[RECORD_ID_FIELD] == operation[RECORD_ID_FIELD] and
            record.id != operation.id
        ]
        for other_write in other_writes:
            other_values = ProductOperationAccess.get_write_field_names(
                other_write)
            merged_values = merged_values.union(other_values)
            _logger.debug("Merged write values: {}".format(merged_values))
        return merged_values

    def _transform_create(self, operation):
        if self._odoo_product.is_sync_active(operation):
            self._create_transformer.transform(operation)
        else:
            _logger.debug("Skip creation operation because the product's "
                          "sync active flag is disabled.")

    def _transform_write(self, operation):
        # if there is a create operation, ignore write
        creation = self._check_create(operation)
        if creation:
            self._transform_create(operation)
            return

        write_values = ProductOperationAccess.get_write_field_names(
            operation)
        log_template = "Product write operation initial values: {}."
        _logger.debug(log_template.format(write_values))

        merged_values = self._merge_write(operation, write_values)
        self._writer_transformer.transform(operation, merged_values)

    def _transform_create_write(self, operation):
        # create or write operation for existed product
        if operation[OPERATION_TYPE_FIELD] == CREATE_RECORD:
            self._transform_create(operation)
        else:
            self._transform_write(operation)

    def _transform_operation(self, operation):
        if operation[OPERATION_TYPE_FIELD] == UNLINK_RECORD:
            self._unlink_transformer.transform(operation)
        elif self._odoo_product.is_existed(operation):
            # only transform a create/write operation for an existing product
            self._transform_create_write(operation)
        else:
            _logger.debug("The product is no longer existed, "
                          "ignore its operations.")

    def transform(self):
        """
        operations are already sorted by ids in descending order
        for each model_name + record_id, there is only one
        product operation left after merge:
        1. unlink is always the last for a model_name + record_id
        thus it will be transformed before other operations that
        are skipped !!!
        2. add create directly, ignore write if there is a create
        3. merge all writes into one then break it into different
        sync operations such as update, price, inventory and image
        """
        _logger.debug("Enter ProductOperationTransformer transform().")
        for operation in self._new_operations:
            log_template = "Transform product operation." \
                           "Operation Id: {0}, Model: {1}, " \
                           "Record id: {2}, Operation type: {3}," \
                           "Write field names: {4}."
            _logger.debug(log_template.format(
                operation.id, operation[MODEL_NAME_FIELD],
                operation[RECORD_ID_FIELD],
                operation[OPERATION_TYPE_FIELD],
                operation[WRITE_FIELD_NAMES_FIELD]))

            record_key = (operation[MODEL_NAME_FIELD],
                          operation[RECORD_ID_FIELD])
            if record_key in self._transformed_operations:
                # process each key only once
                log_template = "Skip processed product operation {}."
                _logger.debug(log_template.format(record_key))
                continue
            else:
                log_template = "First time transform product operation {}."
                _logger.debug(log_template.format(record_key))
                self._transformed_operations.add(record_key)
                self._transform_operation(operation)
