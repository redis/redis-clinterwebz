resource "aws_ecr_repository" "clinterwebz-ecr" {
  name                 = "clinterwebz"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
