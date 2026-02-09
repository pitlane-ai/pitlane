##############################################################################
# Resource Group
##############################################################################

module "resource_group" {
  source  = "terraform-ibm-modules/resource-group/ibm"
  version = "1.4.7"
  # if an existing resource group is not set (null) create a new one using prefix
  resource_group_name          = var.resource_group == null ? "${var.prefix}-resource-group" : null
  existing_resource_group_name = var.resource_group
}

##############################################################################
# VPC
##############################################################################

module "vpc" {
  source            = "terraform-ibm-modules/landing-zone-vpc/ibm"
  version           = "8.12.5"
  resource_group_id = module.resource_group.resource_group_id
  region            = var.region
  prefix            = var.prefix
  tags              = var.resource_tags
  name              = "vpc"
}

##############################################################################
# VSI
##############################################################################

module "vsi" {
  source                = "terraform-ibm-modules/landing-zone-vsi/ibm"
  version               = "4.4.3"
  resource_group_id     = module.resource_group.resource_group_id
  image_id              = var.image_id
  create_security_group = false
  tags                  = var.resource_tags
  subnets               = module.vpc.subnet_zone_list
  vpc_id                = module.vpc.vpc_id
  prefix                = var.prefix
  machine_type          = var.machine_type
  ssh_key_ids           = var.ssh_key_ids
}
