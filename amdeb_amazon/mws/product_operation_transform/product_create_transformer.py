# -*- coding: utf-8 -*-

import logging
from ...models_access import ProductSyncAccess
from ...models_access import OdooProductAccess
from ...models_access import ProductOperationAccess
from ...models_access import AmazonProductAccess
from ...shared.model_names import (
    MODEL_NAME_FIELD, PRODUCT_TEMPLATE_TABLE,
    TEMPLATE_ID_FIELD, RECORD_ID_FIELD,
)


_logger = logging.getLogger(__name__)


class ProductCreateTransformer(object):
    """
    Transform create operation to a create sync.
    Ignore a create operation if it is from a partial variant
    """
    def __init__(self, env):
        self._product_sync = ProductSyncAccess(env)
        self._odoo_product = OdooProductAccess(env)
        self._amazon_product = AmazonProductAccess(env)

    def transform(self, operation):
        # Ignore partial variant creation because there is always a
        # template creation.
        # For non-partial variants, because its template maybe not create
        # or out-of-date, always add a template creation.
        # The correct approach to create variants is to create them
        # from a template in a single batch.
        if ProductOperationAccess.is_product_variant(operation):
            if self._odoo_product.is_partial_variant(operation):
                _logger.debug("Skip partial variant creation operation.")
            else:
                self._product_sync.insert_create(operation)
                self._amazon_product.upsert_creation(operation)
                template_head = {
                    MODEL_NAME_FIELD: PRODUCT_TEMPLATE_TABLE,
                    RECORD_ID_FIELD: operation[TEMPLATE_ID_FIELD],
                    TEMPLATE_ID_FIELD: operation[TEMPLATE_ID_FIELD],
                }
                # we don't check whether the template is created in Amazon
                # or not. Usually all variants are created in a batch.
                is_inserted = self._product_sync.insert_create_if_new(
                    template_head)
                if is_inserted:
                    _logger.debug("A template creation sync is inserted "
                                  "for this non-partial variant.")
                    self._amazon_product.upsert_creation(template_head)
        else:
            if self._odoo_product.is_multi_variant(operation):
                # template create sync is inserted by one of its variants
                _logger.debug("Skip creation operation for "
                              "multi-variant template.")
            else:
                self._product_sync.insert_create(operation)
                self._amazon_product.upsert_creation(operation)
