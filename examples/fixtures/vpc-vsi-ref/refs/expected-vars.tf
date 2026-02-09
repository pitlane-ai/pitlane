variable "ibmcloud_api_key" {
  description = "IBM Cloud API key used to provision resources"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "IBM Cloud region where resources will be deployed"
  type        = string
}

variable "prefix" {
  description = "Prefix to apply to all resource names"
  type        = string
}

variable "resource_group" {
  description = "Name of an existing resource group. If null, a new one is created."
  type        = string
  default     = null
}

variable "resource_tags" {
  description = "List of tags to apply to created resources"
  type        = list(string)
  default     = []
}

variable "ssh_key_ids" {
  description = "List of SSH key IDs to inject into the VSI"
  type        = list(string)
}

variable "image_id" {
  description = "ID of the OS image for the VSI"
  type        = string
}

variable "machine_type" {
  description = "VSI machine type profile (e.g. cx2-2x4)"
  type        = string
  default     = "cx2-2x4"
}
