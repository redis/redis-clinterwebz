resource "aws_security_group" "inbound" {
    name = "allow_ssh"
    description = "Allow inbound ssh"
    vpc_id = aws_vpc.clinterwebz-vpc.id

    ingress {
        from_port = 22
        to_port = 22
        protocol = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    egress {
        from_port = 0
        to_port = 0
        protocol = -1
        cidr_blocks = ["0.0.0.0/0"]
    }

    tags = {
        Name = "ssh inbound"
    }
}