variable aws_region {
    type                                    = string
    description                             = "AWS Region"
    default                                 = "us-east-1"
}

variable aws_access_key {
    type                                    = string
}

variable aws_secret_access_key {
    type                                    = string
}

variable "vpc_cidr" {
    default                                 = "10.20.0.0/16"
}

variable "subnet_cidrs" {
    type                                    = list
    default                                 = ["10.20.0.1/24", "10.20.0.2/24", "10.20.0.3/24"]
}

variable availability_zones {
    type                                    = list
    default                                 = ["us-east-1a", "us-east-1b"]
}

variable ami_id {
    type                                    = string
    ami                                     = "ami-09db26f1ef0a9f406"
}