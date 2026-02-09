# IBM Cloud VPC with VSI

This Terraform configuration provisions an IBM Cloud Virtual Private Cloud (VPC)
and deploys a Virtual Server Instance (VSI) into it using curated
Terraform IBM Modules (TIM).

## Architecture

- **VPC**: Created using the `terraform-ibm-modules/landing-zone-vpc/ibm` module
  with subnets across availability zones and public gateway support.
- **VSI**: Deployed using the `terraform-ibm-modules/landing-zone-vsi/ibm` module
  into the VPC subnets, with configurable machine type and SSH access.

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.3.0 |
| ibm | >= 1.49.0 |

## Usage

```hcl
module "vpc" {
  source  = "terraform-ibm-modules/landing-zone-vpc/ibm"
  version = "8.12.5"
  ...
}

module "vsi" {
  source  = "terraform-ibm-modules/landing-zone-vsi/ibm"
  version = "4.4.3"
  vpc_id  = module.vpc.vpc_id
  subnets = module.vpc.subnet_zone_list
  ...
}
```

## Inputs

| Name | Description | Type | Required |
|------|-------------|------|----------|
| ibmcloud_api_key | IBM Cloud API key | string | yes |
| region | IBM Cloud region for deployment | string | yes |
| prefix | Prefix for naming resources | string | yes |
| resource_group | Existing resource group name | string | no |
| ssh_key_ids | List of SSH key IDs for VSI access | list(string) | yes |
| machine_type | VSI machine type profile | string | no |
| image_id | VSI image ID | string | yes |
| resource_tags | Tags to apply to resources | list(string) | no |

## Outputs

| Name | Description |
|------|-------------|
| vpc_id | ID of the created VPC |
| vpc_name | Name of the created VPC |
| subnet_zone_list | List of subnet objects with zone info |
| vsi_ids | List of VSI instance IDs |
| vsi_list | List of VSI details |
