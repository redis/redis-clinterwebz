resource "aws_vpc" "clinterwebz-vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "ClinterwebzVPC"
  }
}

resource "aws_internet_gateway" "clinterwebz-igw" {
  vpc_id = aws_vpc.clinterwebz-vpc.id
  tags = {
    Name = "IGW"
  }
}

resource "aws_subnet" "public-1a" {
  vpc_id                  = aws_vpc.clinterwebz-vpc.id
  cidr_block              = var.subnet_cidrs[0]
  availability_zone       = var.availability_zones[0]
  map_public_ip_on_launch = true
}

resource "aws_route_table" "public-1a-route-tbl" {
  vpc_id = aws_vpc.clinterwebz-vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.clinterwebz-igw.id
  }
}

resource "aws_route_table_association" "public-1a-route-tblassoc" {
  subnet_id      = aws_subnet.public-1a.id
  route_table_id = aws_subnet.public-1a.id
}
